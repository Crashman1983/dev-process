# Changelog — dev-process

Die vollständige Sub-Projekt-Historie, aus dem README hierher ausgelagert
(das README orientiert, dieses Dokument archiviert). Neue Releases nennen im
README nur die aktuelle Version und schreiben die Historie hier fort.

## Status-Narrativ (chronologisch)

SP1 (Foundation) + SP2 (Architektur-Onboarding) + SP3
(feature-registry, github-issues, contracts-drift) + SP4 (git-hooks,
contract-first, parity, security-floor) + Capstone (command-adapters,
`v1.0.0` — das volle Command-Set des Referenzprojekts, harness-nativ) + SP7 (ci-adapters:
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
Prozess-Zweig: pre-push prüft die **gepushten Commits** statt des
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
ceiling" + Cockpit-Docstring + README; Moduldoc + Cockpit per
Template-Test gepinnt)
ausgeliefert, `v1.33.0`.

SP49 (KISS-Cleanup — ein Owner je Verhalten, aus drei parallelen
Tiefen-Sweeps (Dead Code, Duplikate, Doku-vs-Code): check_review besitzt die
Plan-Feld-Grammatik und _unfenced (check_issues/trace importieren; Issue-Regex
vereinheitlicht, Cross-Repo-Refs clearen jetzt auch das Review-Gate),
check_decisions besitzt adr_exists (3 divergente Kopien ersetzt), das
Review-Bundle importiert die Kernel-Block-Extraktion (Zweitblock → ehrlich
unavailable statt still der erste), gh_json ein Owner im github-issues-Modul;
nicht-importierbare Zwillinge (sbom/security-floor-Git-Helfer,
EARS/Epic-Heuristik) per Template-Test gepinnt. Funktional: sbom-Beispiel-Policy
no-opte auf Root-Manifesten (bare+**/-Paare), tote Manifest-Globs ohne Parser
entfernt, `sbom` fehlte in allen drei Adapter-Modullisten (Test pinnt auf
copier.yml), gh_board --push-No-op-Stub entfernt, github-master meldet leeren
Mirror advisory statt still OK, trace-FINDING-Matcher verlangt key=value; dazu
12 Doku-Kohärenz-Fixes ("one tier weaker" gestrichen, DoR/DoD-Abweichungskanäle
getrennt, Copilot-Review-Prompt trägt die Grammatik, u. a.)) ausgeliefert,
`v1.34.0`.

SP50 (Tiefenaudit über den bereinigten Stand, vier unabhängige Blickwinkel
mit Ausführungsmandat — adversarial, Kohärenz, Fresh-Adopter, Robustheit:
1 Blocker geschlossen (Fence-Tracking längenbewusst — gequotete Waiver in
verschachtelten Fences clearten Review-/Issue-Gate), SP49-Regression gefixt
(nur echte Issue-Refs zählen als clearende work-ids; Ref-Grammatik nach
check_review verschoben, ein Owner), OSError-Diagnosen statt Tracebacks,
security-floor mit Regex-Backtracking-Budget + Zero-in-Scope-Note,
gate_runner mit Gate-Timeout + bytecode-frei, letzte adr_exists/_unfenced-
Kopien konsolidiert, gh_board-Argument-Hygiene, BOOTSTRAP-Update-Rezept für
HEAD-Installs, start-here-Reihenfolge + `git init -b main`,
Commit-Traceability-Konvention; Adopter-Verdict: Solo-Dev erreicht grünen
Gate-Lauf + ersten reviewten Change ohne Hilfe; Report
`.process-work/reviews/2026-07-10-sp50-deep-audit.md`) ausgeliefert,
`v1.34.1`.

SP51 (State-of-the-art-Abgleich geschlossen — sechs Lücken aus der Recherche
(DORA, Diátaxis/arc42, Supply-Chain, Diagrams-as-Code, KI-Guardrails):
`testing.md` als Core-Doc (Suite-Form als Pyramiden-Heuristik, Property-based,
Regression-Pins, Mutation-Testing auf kritischer Logik, ehrliche
Coverage-Decke — Trend statt Schwellen-Gate; via Regel 5 +
Review-Checkliste verdrahtet), `releases.md` als Core-Doc (SemVer,
kuratiertes Changelog, Tag-Ritual mit Versions-Dreiklang-Invariante;
via commits.md verdrahtet), Threat-Frage für Tier 3 in Brainstorm +
Review-Checkliste („Was könnte ein Angreifer mit dieser Änderung?" —
Assets/Inputs/Trust-Boundaries), Diagrams-as-Code-Konvention (Mermaid im
Markdown, diffbar im PR; Gate parst weiterhin keine Diagramme) in
arch-docs-Moduldoc + Overview-Scaffold, Plattform-Hygiene im
Onboarding-DoR (Secret Scanning + Push Protection, Dependabot/Renovate —
ehrlich als Netz-Dienste gerahmt, kein hermetisches Gate),
Branch-Lebensdauer „Tage, nicht Wochen" in commits.md (Small-Batch-Befund
hinter Trunk-based)) ausgeliefert, `v1.35.0`.

SP52 (Divers-Audit über v1.35.0 — vier bewusst neue Blickwinkel: Pragmatiker/
Ökonomie (Verdict „Prozess mit ungewöhnlich wenig Theater": ~5.4k Token
Lese-Steuer/Session, Gates 0.2–0.8s, Over-Engineering-Kandidaten
freigesprochen), Multi-Harness-Degradation (9 Render-Kombos), Lebenszyklus
(Upgrades v1.13.0→HEAD konfliktfrei byte-identisch; 10x-Wachstum <0.9s) und
Technical Writer über die SP48–51-Prosa. Gefixt: Copilot-Anker erhält die
Route zu workflow/commits, BOOTSTRAP-„Later" ohne --skip (stale Kernel nach
Upgrade reproduziert) + Hooks-Neuinstallations-Hinweis, trace ohne
Bare-Digit-Rauschen (#7 matchte 68/68 Pläne), Bundle mit --plan-Filter und
hartem Unknown-Flag-Fehler, Soft-Note für nicht archivierte Tier-2+-Pläne,
doc-drift scannt die Copilot-instructions-Datei, gate_runner benennt die
Hand-Edit-Ursache, No-CI-DoR erfüllbar (Hooks als Authority), Quick-Fragen
mit einem Owner in workflow.md, Retention-Ehrlichkeit, R2 besitzt die vier
Akzeptanz-Fälle, ~15 Writer-Präzisionsfixes; Report
`.process-work/reviews/2026-07-10-sp52-diverse-audit.md`) ausgeliefert,
`v1.35.1`.

SP53 (Methodik-Eignungsprüfung geschlossen — die zwei Lücken aus dem
Prinzipien-Check der Kette Brainstorm→EARS→Plan: der **EARS-Musterkatalog**
in der DoR-Doc (alle fünf Formen — ubiquitous/event/state/unwanted/optional —
mit Unwanted-behaviour als natürlicher Form der von R2 geforderten
Negativ-Fälle) und der **Spike-Pfad** in workflow.md für ergebnisoffene
Arbeit (timeboxed, Output ist Wissen — Journal/Design/Decision Record —,
nie Produkt-Code; Folge-Feature läuft durch den normalen Zyklus statt den
Prototyp zu befördern; Timebox-Stopp ist Erfolg)) ausgeliefert, `v1.36.0`.

SP54 (Cross-Platform-Haertung: `git` + `uv` als einheitlicher Runtime-Vertrag
auf Linux, macOS und Windows; PEP-723-Gate-Runner ohne systemweites Python oder
PyYAML; portable Python-Implementierungen fuer Hook-Installation, Hook-Logik
und Issue-Body-Erzeugung bei kompatiblen Shell-Launchern; Claude, Copilot und
AGENTS.md unabhaengig kombinierbar; OS-Smoke-Matrix; Manifestwerte fail-closed
validiert; Release-Tag muss zur Projektversion passen) ausgeliefert, `v1.37.0`.

SP55 (spec-deepening: Spezifikationsphase vertieft — Anleihen aus GitHub
Spec Kit, schema-erhaltend (Analyse: `docs/analysis/2026-08-06-speckit-comparison.md`).
`[NEEDS CLARIFICATION: …]`-Marker-Konvention im Brainstorm statt stiller
Annahmen; `design-template.md` als Core-Doc-Scaffold (Intent, Constraints,
Touchpoints, nummerierte EARS-ACs, Alternativen, offene Fragen, Tier-3-
Threat-Frage); Review-Checkliste um „Specification quality" erweitert
(testbare Kriterien, ehrlich aufgelöste Fragen, Was/Wie-Trennung, DoR-R2-
Twins). Fünftes **Core-Gate** (`check_clarification.py`): unaufgelöster
Marker in einem *aktiven Plan* hart (Plan setzt genehmigtes Design voraus),
im aktiven Design nur Note (mid-flight bleibt grün), Archiv ist Historie;
Fenced-Block = Zitat wie beim Review-Gate) ausgeliefert.

SP56 (lean-standard: das große Refactoring auf den Standard-Stack
GitHub + Spec Kit + pre-commit + dev-process-Kernel, nach unabhängigem
Design-Review (Report: `.process-work/reviews/2026-08-06-speckit-hybrid-design-review.md`).
**Abgebaut:** GitLab-CI-Adapter, parity, attention.py/who_is_working.py
(GitHub-UI übernimmt), story_order + Arbeits-Log-Achse der Registry,
eigener Hook-Installer, artifact-v1-Zertifikatsritual, Telemetrie auf die
drei Ziel-KPIs (Konvergenz, Kosten, CFR), Profile/Toggles auf das
Standard-Setup mit einzigem `regulated`-Schalter, contract-first +
contracts-drift zu `contracts` verschmolzen. **Umgebaut:** feature-registry
zum Feature-Inventar (Capability → Akzeptanz → Test, hermetisch), Hooks auf
das pre-commit-Framework, github-master registry-frei (Snapshot nach
Issue-Nummer, DoR-at-rest, Board-Konsistenz), Review auf eine
Attestierung mit opt-in Diff-Digest (verifiziert statt Ritual).
**Gebaut:** `speckit`-Modul als Standard-Spezifikationsweg —
Constitution-Pointer mit Gate-Guard, EARS-/Test-Pflicht-Overrides,
Command-Wrapper mit Kernel-Pflichten, clarification-Gate über `specs/`,
publish_and_prune-Merge-Ritual mit verifiziertem Publish + SC-Accounting
und Flow-Forward-Degradation. Produktrahmen-Wechsel im README dokumentiert,
Exit-Szenario (Pin einfrieren) festgehalten. Dazu der Token-Lean-Pass
(process_context.py, Prime-Diät, analyze/converge nur noch Tier 3) und der
Windows-Pfad-Fix (kein `|` mehr in Template-Pfaden — die OS-Smoke-Matrix ist
wieder grün)) ausgeliefert, `v2.0.0` — **Breaking**: Modul-Keys und
Install-Dialog geändert; Migration bestehender Adopter über `copier update`
mit explizitem `modules`-Dict (BOOTSTRAP, "Later").

SP57 (reference-backflow: die vier Prozess-Lektionen aus dem Live-Betrieb des Referenzprojekts,
die dem generischen Kern nach der Adoption nachweislich noch fehlten —
Regel 1 geschärft (Sub-Agent-Summaries sind `[assumption]` bis zur
Stichprobe; Stop-Wort „source?" ⇒ Tool-Beweis oder Rückzug),
Review-Runden-Cap im Workflow (nach zwei erfolglosen Review→Fix-Runden
zurück in die Planung — das Review-Pendant zur Zwei-Versuche-Regel 6),
Bookkeeping-Disziplin in `commits.md` (Journal/Plan/State fahren im
Arbeits-Commit, keine `record`-Ketten; SSOT-lose Evidence ins
Issue-Kommentar) und der Anchor-Budget-Check im doc-drift-gate
(Anchor > 200 Zeilen ⇒ Note, nie Fail — der mechanische Wächter für den
„driftet es beim Refactor?"-Diskriminator). Dazu zwei Brownfield-Fixes am
Decision-Records-Gate, die ADR-Korpus-Übernahme im Referenzprojekt aufgedeckt hat:
Status-Enum um `Rejected` (Vorschlag, der nie galt) und `Deprecated`
(galt einmal, jetzt abgeraten) erweitert — sonst bliebe ein toter
Vorschlag ewig `proposed` —, und der Seed-Record von `adr-0001` auf
`adr-0000` umnummeriert, damit ein bestehender Korpus, der bei 0001
beginnt, kollisionsfrei einziehen kann. Ausgeliefert als `v2.1.0`.

Lizenzwechsel (2026-08-07, nach v2.1.0): von der Prosperity Public
License 3.0.0 (nicht-kommerziell) zu **Apache-2.0** — der Kern ist bewusst
offen (Open-Core-Strategie: künftige kommerzielle Zusatzkomponenten bleiben
separate Werke). Zugleich die MIT-Attribution für die zwei von GitHub
Spec Kit abgeleiteten Templates nachgezogen (`THIRD-PARTY-NOTICES.md`,
auch gerendert in Adopter-Repos; Provenienz-Kommentare in den Dateien).

SP58 (skill-bypass-closure: Beobachtung im Referenzprojekt, dass topic-getriggerte
Dritt-Skills (Superpowers-Brainstorming/-Planning) mit eigenen Datei-
Konventionen die artefakt-präsenz-abhängigen Pflichten lautlos umgehen
können — ein Plan, der nie in `.process-work/plans/` landet, löst weder
Clarification- noch Review-Präsenz aus. Antwort auf beiden Ebenen:
`journal-state-plans.md` schreibt „Plans have exactly one home" fest
(Skills helfen *in* Phasen, das Artefakt hat genau ein Zuhause), und das
Review-Gate bekommt den **Unhomed-Plan-Detector** — eine `tier: 2+`-
Deklaration außerhalb der sanktionierten Homes (`.process-work/`,
`specs/`, `docs/process/`, Harness-Verzeichnisse; Archive sind Historie)
ist hart; Tier 0/1 und gefencte Zitate bleiben außen vor. Dazu
**spec-before-plan** im Speckit-Gate: ein aktiver Tier-2+-Plan
referenziert sein `specs/`-Verzeichnis oder trägt eine begründete
`spec-waived:`-Zeile — die Spec-Kit-Interrogation zu überspringen ist
eine dokumentierte Entscheidung, nie ein stilles Verhalten) ausgeliefert,
`v2.2.0` (enthält auch den Apache-2.0-Lizenzwechsel unten).

SP59 (downstream-backflow: die vier generalisierbaren Beiträge aus dem
privaten DATEV-Fork, per Patch-Handoff übernommen (der Fork darf keine
PRs stellen) — Copier-Render-Cache in den Tests (jedes Answer-Set
rendert einmal pro Session, jeder Test bekommt seine Kopie; volle Suite
von ~4,5 min auf ~1,5 min), Gate-Preflight vor dem Review-Bundle (rote
Gates ergeben kein review-fertiges Bundle; `--skip-preflight` als
bewusster Ausweg), begrenzte Delta-Re-Reviews (`--since` mit
Voll-Artefakt-Bindung, mitgeführten Vorbefunden und Tier-3-Ablehnung)
und der advisory Finding-Ratchet (`gate=judgement|possible|<rule>` an
FINDING-Zeilen — `possible` markiert Automatisierungskandidaten als
Note, nie blockierend). Bewusst NICHT übernommen: Model-Routing,
CODEOWNERS-Härtung, Pflicht-SBOM, Plattform-Fixierung (Fork-lokal,
deckungsgleich mit dem Lean-Pass) und das decision-adoption-Modul
(geparkt bis Nutzungsevidenz vorliegt — die Intent-Achse trägt die
leichte Version bereits)) ausgeliefert, `v2.3.0`.

SP60 (engine-freiheit + hygiene, aus dem Live-Betrieb des Referenzprojekts der
SpecKit/Superpowers-Kombination: „The execute engine is free, the
artifacts are not" — Subagent-per-Task-Engines sind im Execute
sanktioniert, solange die Artefakt-Invarianten halten und die
Merge-Review die attestierte bleibt; der **Prose-Tier-Detector** im
Review-Gate macht den Drittskill-Fehlermodus laut (Plan erwähnt „Tier
N", deklariert aber keine `tier:`-Zeile ⇒ alle tier-gekeyten Gates
unbewaffnet — live auf #651 gefunden); dazu **„Merge leaves no
residue"** in commits.md (Branch löschen, `git worktree
remove`/`prune`) und der dispatchbare **cleanup-branches-Workflow**
(patch-identitäts-basiert, Dry-Run-Default, Open-PR-Schutz) im Repo
und im Template) ausgeliefert, `v2.4.0`.

SP61 (sichtbarkeits-paket, aus dem Lebenszyklus-Review des Maintainers: **Issue bei
der Idee statt beim Plan** — das Einflussfenster des Menschen ist die
Spec-/Design-Phase, also entsteht das Tracking-Issue beim Brainstorm-
Eintritt und eine aktive `specs/*/spec.md` ohne `issue:`-Zeile ist hart
(issue-before-spec im Issues-Gate); **Stage-Publishing** —
`publish_and_prune --stage` postet die fertige Spec (und Design) als
datierten Read-only-Snapshot-Kommentar ans Issue, prunt nichts, und
neue Issue-Kommentare sind Clarify-Input vor `/plan`; **Review-
Ökonomie für Subagent-Engines** — Task-Reviews nur für Owner-/
Integrations-Tasks (Mechanik im Sammel-Checkpoint), Runde 2+ als
`--since`-Delta, und die finale Whole-Branch-Review des Engines IST
die attestierte Merge-Review — ein Deep-Review auf dem stärksten
Modell statt zwei (~5 statt ~9 Läufe pro #651-großem Paket))
ausgeliefert, `v2.5.0`.

Modell-Routing als Harness-Default (`model:`-Frontmatter auf den
Phase-Commands: `/brainstorm` und `/plan` auf dem stärksten Modell
(Urteilsdichte — ein Spec-/Plan-Fehler kostet sein Vielfaches
stromabwärts), `/review` auf `opus`, Execution erbt das
Sitzungs-Arbeitsmodell; die `/speckit-*`-Commands bleiben unberührt, da
ein Spec-Kit-Update sie überschreibt — Routing lebt in den
Wrapper-Commands; Doku im speckit-Modul aktualisiert; kein neues Gate,
keine Config-Achse — Routing bleibt Engine-/Harness-Verhalten),
`v2.5.1`.

Runden-Ökonomie der Review-Schleife dokumentiert (aus dem Maintainer-Befund „bei
jeder Abweichung läuft die gesamte Kette": das `--since`-Delta-Bundle
existierte seit v2.3.0, aber kein Dokument und kein Command lehrte es —
`/review`, workflow.md (Review) und verification-independence.md
beschreiben jetzt die drei Preisregeln: Findings einer Runde bündeln,
ein Fix-Pass, ein Push (jeder zusätzliche Head-Commit bezahlt die
Push-Gates/Tests erneut); Runde 2+ als Delta-Bundle über `--since`
(Volldiff bleibt digest-gebunden, Tier 3 liest immer voll); einmal
rebasen, vor der ersten Runde — jede spätere Rebase entwertet die
Digests), `v2.5.2`.

SP62 (längsschnitt, aus dem Befund im Referenzprojekt „53 fix-Commits in 5 Tagen, ein
Scope-Cluster mit 13 Fixes, jeder einzeln durch alle Gates": der Prozess
regierte das einzelne Paket, hatte aber kein Organ für Muster ZWISCHEN
Paketen — **fix-Cluster-Advisory** (`process_kpis clusters`: Rule 6
sessionübergreifend, der Zähler lebt in git; Debug-Command, workflow.md
und Review-Checkliste tragen die Stopp-Regel „dritter Fix am selben
Verhalten = fehlende Spezifikation"); **Invarianten-Heimat** (Decision-
Record-Typ `invariant` für featureübergreifende Verhaltensregeln,
`## Test`-Pflicht als Enforcement-Zwilling ab Accepted, decisions-Gate
prüft); **Degradations-Schulden** (`review-waived:`/`spec-waived:` ohne
Issue-Ref → Note „a debt with an owner"); **KPI-Trigger** (monatlicher
process-kpis-Workflow — ein KPI ohne Trigger existiert nicht);
**`/finish`** (`finish.py`: der Merge-Schwanz als EIN Verdikt — clearing
pass, grüne Gates, sauberer Tree, dann der Rest-Ritus in Reihenfolge;
read-only, gegen die beobachteten Tail-Ausfälle #652/#653/#660))
ausgeliefert, `v2.6.0`.

Slice-Ökonomie nachgeschärft (aus dem #688-Befund „50 Tasks, extrem
lang": **Task-Korn** — ein Task = ein Verhalten, Test UND Implementierung;
TDD-Reihenfolge lebt IM Task, nie als Task-Paar (der Task ist die Einheit
von Planung, Checkbox, Gate-Lauf und Bericht — 50 Tasks, die 30 sein
könnten, zahlen das Ritual zwanzigmal umsonst); **Tier pro Stage** — bei
Stage-Merges trägt jede Stage ihren eigenen Tier, eine verhaltensneutrale
Extraktions-Stage mit mechanischem Beweis ist Tier 2, auch wenn die
verhaltensändernde Stage Tier 3 ist (risk-tiers.md); **Mechanik vor
Urteil** — alle mechanischen Detektoren laufen VOR dem Review-Bundle und
ihre Ergebnisse wandern hinein, der Modell-Reviewer verifiziert die
Mechanik-Schicht statt sie zu entdecken (ein grep-barer Befund kostet
mechanisch Cents, per Review eine Runde)), `v2.6.1`.

[P]-Gruppen wirklich nutzen („parallel edit, serial commit": [P]-Tasks
laufen als gleichzeitige Subagents im selben Worktree — Subagents
editieren ihr disjunktes Datei-Paket und liefern Test-Evidenz, committen
nie; der Orchestrator serialisiert den Schwanz jedes Tasks — atomarer
Commit, Checkbox, Gate — in Abhängigkeitsreihenfolge; /plan schärft
[P] auf „kein geteilter Berührungspunkt", inkl. Barrel-Exports,
Manifeste, generierte Indizes — ein falscher Marker wäre eine
Working-Tree-Kollision), `v2.6.2`.

SP63 (owner-loop, aus dem Maintainer-Befund „ich reviewe die Slices kaum — und
verstehe die Specs oft nicht": der Mensch wird ein echter Knoten des
Loop-Graphen, mit definierten Eingangs-Kanten statt Polling —
**Owner brief** (Pflicht-Vorspann jeder Spec: fünf Klartext-Sätze ohne
Jargon/Dateinamen — Was/Warum/sichtbare Änderung/Risiko/„Your call";
führt den staged Issue-Kommentar an, macht das Einflussfenster
benutzbar); **`human_digest.py`** (die Eingangs-Kanten als EINE Seite:
wartende Specs samt Brief + offenen Fragen, Merges der letzten N Tage,
stehende Waiver-Schulden, Fix-Cluster; read-only, fehlende Quellen
benannt statt still leer); **Sampling-Audit** (ein gemergtes Paket pro
Woche, deterministisch per ISO-Woche gewählt — kein Re-Rollen; Review
by exception statt Diff-Konkurrenz zum Modell-Reviewer,
verification-independence.md); **owner-digest-Workflow** (wöchentlich
Mo + Dispatch, Digest in die Step-Summary)) ausgeliefert, `v2.7.0`.

SP64 (speckit-presence, aus dem Befund im Referenzprojekt „Slices 009–016 liefen am
stärksten Gate vorbei": die Spec-Kit-Pläne leben in `specs/<dir>/plan.md`
und werden nie archiviert — das Review-Presence-Gate scannte nur
`.process-work/plans/archive/` und konnte den Standardweg nicht sehen —
**Speckit-Presence** (`speckit_unreviewed` in check_review: voll
abgehaktes tasks.md + Tier-2+-Plan ohne Waiver braucht den clearing
pass; `finish.py` blockt hart am Merge-Ritus, das Review-Gate meldet
als Note — hart am Push würde jeden Push zwischen letztem Tick und
Review röten; commits.md benennt die Speckit-Variante des
Archiv-Schritts: publish_and_prune statt Archiv-Move, finish druckt
die fertigen Verzeichnisse einzeln); **Owner-Brief-Note** (speckit-Gate:
spec.md ohne Owner-brief-Sektion → Note — 2 von 6 neuen Specs im Referenzprojekt
hatten den Brief vergessen); **Waiver-Ehrlichkeit** (ein Plan mit
`issue:`-Anker besitzt seine Waiver dort — nur trackerlose Waiver
werden geflaggt; Digest gleichgezogen); **ADR-Rauschen** (Intent-Note
entfällt für rejected/superseded — historische Records haben keine
Endorsement-Achse)) ausgeliefert, `v2.7.1`.

Zwei Gate-Defekte aus dem frischen Klon des Referenzprojekts (der erste kalte
Prüfstand nach Wochen warmer Sessions): **Digest-Bindung ehrlich
degradiert** — nach Rebase-Merge + Branch-Löschung existieren die
Pre-Merge-SHAs in keinem frischen Klon; nicht auflösbare
Artifact-Commits sind jetzt Note („unverifiable here") statt hartem
Rot, das rückwirkend jeden Klon für jede korrekt gebundene historische
Review röten würde; ein Digest-MISMATCH bleibt hart. **Tier-Deckel in
der Presence-Arithmetik** — die REVIEW-Grammatik deckelt tier bei 3;
ein Plan auf erweiterter Downstream-Skala (`tier: 4/5`) cleart an der
gegateten Decke (min(tier,3)) statt an einer unerfüllbaren Latte,
Archiv- und Speckit-Pfad gleichermaßen, `v2.7.2`.

Test-Ökonomie als generisches Muster (aus der Maintainer-Frage „voller Testlauf
bei jeder Änderung?": **Selektion nah am Edit, Vollständigkeit nah am
Merge** — testing.md trägt die Staffel: pro Task/Push die gescopte
Menge (Modul-Graph/`vitest related` oder auditierbare Modul-Karte) mit
ehrlichen Voll-Lauf-Triggern für alles, was nicht über Imports wirkt
(Config, Tokens, globale Styles, Schema, DI, Fixtures); am
Merge-Boundary die VOLLE Suite genau einmal für das ganze Batch —
mehrere Änderungen teilen sich einen Voll-Lauf, Selektion ist nie das
letzte Netz; finish.py druckt den Voll-Suite-Schritt vor dem Merge),
`v2.7.3`.

Push- und Zertifikats-Ökonomie (aus dem Maintainer-Befund „Deploy 20 min, Push-Gate
ähnlich": **Push an Kohärenzpunkten, nicht pro Commit** — die Push-Gates
bepreisen die gepushte Spanne, fünf zusammengehörige Commits in einem
Push kosten einen Gate-Lauf; Grenzen: vor Bundle-Bau, vor Session-Ende,
oft genug für die Parallel-Sichtbarkeit (commits.md). **Bezahlte
Vollständigkeit ist übertragbar** — der Boundary-Volllauf schreibt die
Zertifikate, auf die spätere Gates memoisieren (Coverage-Tree-Cert), in
der zertifizierenden Konfiguration verdient, nie behauptet; ein Deploy-
Gate auf demselben Baum wird zum Memo-Hit statt zur Doppelzahlung
(testing.md)), `v2.7.4`.

Zertifikats-Transfer auch bergab (aus einem Live-Befund des Maintainers „Push-Gate zieht
die volle Suite, gleich danach der Boundary-Lauf nochmal, ohne
Änderung dazwischen": **stärkere Evidenz ersetzt schwächere** — ein
Voll-Lauf-Trigger am Push darf auf ein Zertifikat memoisieren, das
denselben Baum in einer Obermengen-Konfiguration deckt (Coverage-Lauf
⊇ einfacher Lauf); die Reihenfolge am Kohärenzpunkt ist damit
Boundary-Lauf → Push → Review → Merge — ein Voll-Lauf pro Batch, alle
späteren Gates lesen das Zertifikat statt es neu zu verdienen;
Klarstellung: der Review-Preflight fährt nur die Prozess-Gates, nie
die Suite), `v2.7.5`.

Suite als gemanagtes Asset (aus dem Maintainer-Befund „immer noch extrem viel
Zeit für Tests" — gemessen: die Vitest-Suite wuchs in zwei Wochen um
43 %, 69 E2E-Specs × 2 Plattformen, und Stabilitätsbeweise liefen als
5× Voll-Suite: **E2E-Budget pro Feature = 1, Floor UND Ceiling** — ein
wachsendes Feature ersetzt seinen E2E-Beweis, Plattform-Varianten nur
bei abweichendem Verhalten, Konsolidierungs-Pässe sind Wartung, jeder
pensionierte Test braucht einen benannten billigeren Ersatz;
**Stabilitätsbeweise scoped × N, voll × 1** (testing.md); **Test-
Estate-Trend im Owner-Digest** — Unit-/E2E-Dateizahlen jetzt vs. vor
14 Tagen, git-basiert, read-only — Wachstum wird sichtbar, bevor es
sich wieder wie heute anfühlt), `v2.7.6`.

Vier-Zustands-Pflicht für UI-Stories (aus der Härtungswellen-Analyse:
~¼ der Fixes im Referenzprojekt waren Kalt-/Leer-/Offline-Zustände — „unknown stock
als leer gerendert", Scope-Fallback beim Laden; das Spec-Template
verlangt jetzt pro berührter Oberfläche die Tabelle loading / empty /
error / **unknown** mit je einem erwarteten Verhalten — die DoR-R2-
Zwillinge, für UI konkretisiert; „unknown" ist der Zustand, der
unbenannt kaputt ausgeliefert wird: not-yet-resolved ist weder leer
noch Fehler), `v2.7.7`.

Records sind Leitplanken, kein Beton (auf Wunsch des Maintainers festgehalten:
ADRs und Contracts DÜRFEN geändert werden, wenn die Lösung dadurch
dauerhaft tragfähiger, technisch besser oder klarer wird — das allein
ist hinreichender Grund; die zwei Ehrlichkeitspflichten sind die ganze
Latte: benennen, was besser wird und warum es langfristig hält (nicht
bloß „gerade bequemer"), und die Änderung im selben Aufwand wie der
Code, der sie voraussetzt (Rule 4) — Supersession bzw. versionierter
Contract-Wechsel mit allen Konsumenten, nie stille Drift; adr/README
und contract-first.md tragen den Grundsatz), `v2.7.8`.

SP65 (reference-upstreaming: vier Prozess-Erfindungen aus dem Referenzprojekt, die generisch
tragen, in den Kern gehoben. **Launch-Owner** (`gate_invoke.py`, reines
stdlib: die eine Stelle, die entscheidet, womit ein PEP-723-deklarierendes
Skript gestartet wird — Kinder des Runners, `finish.py` und das
Review-Bundle laufen darüber; „nicht startbar" wird getrennt von „rot"
gemeldet, denn ein Runner, der nicht anläuft, ist ein Launch-Problem mit
anderem Owner als eine Regression). **Hook-Doktor** (dasselbe Modul:
`.pre-commit-config.yaml` neben gesetztem `core.hooksPath` heißt, jede
Registrierung ist stumm — im Referenzprojekt 25 Tage lang unbemerkt; gate_runner
und finish blocken hart, ein nie installierter Hook ist eine Note bzw.
ein finish-Blocker: ein fehlender Check ist ein Blocker, nie ein Skip).
**Push-verankerte Presence** (check_review: ein aktiver Tier-3-Plan, den
DIESER Push trägt — Datei im gepushten Bereich oder Issue per
Closing-Trailer/`(#N)`-Subject beansprucht — braucht den clearing pass
hart auf dem Push nach main/master, als Note sonst; das Ziel liest das
Gate aus `PRE_COMMIT_REMOTE_BRANCH` des pre-commit-Frameworks oder
`PROCESS_PUSH_TARGETS` eines eigenen Hooks; bekannte Grenze: ein
serverseitig gemergter PR pusht main nie lokal — dort bleibt finish.py
der Stop). **finish auf Branch-Besitz gescoped** (nur Pläne, die der
Branch trägt oder beansprucht, sind seine Review-Schuld und
Archivierungspflicht — ein fremdes Entscheidungspapier im Baum blockte
im Referenzprojekt einen unbeteiligten Branch). **UI-Wiederverwendungspflicht**
(DoR R5 / DoD D7: Reuse-Map vor Implementierung, Konsumenten-Nachweis
danach; review-checklist „Surfaces": nichts geclippt, 24-px-Ziele nach
WCAG 2.5.8, zugänglicher Name auf jedem Button/Link, nichts verdeckt,
vier Zustände, beide Themes — Stack-Guides schärfen, senken nie).
**Ratchet-Muster** (testing.md: Baseline pinnt Legacy, neue Befunde und
verwaiste Ausnahmen scheitern; die Baseline kann nur schrumpfen) und
**„Unmessbar ist nicht rot"** (Mess-Gates verweigern auf belastetem Host
mit eigenem Exit-Code, EX_TEMPFAIL, statt zu scheitern)) ausgeliefert,
`v2.8.0`.

Zwei Token- und Zeitsparer, auf die Maintainer-Frage „was lässt sich noch per
Skript automatisieren": **Note-Ledger im gate_runner** (jede Gate-Note
landet im Kontext des Agenten, und die Notes sind konstruktionsbedingt
stabil — Pre-Adoption-Zustände, Platzhalter, Freshness-Hinweise — also
kostete jeder Push dieselben Zeilen und begrub die eine, die sich
geändert hat; der Runner merkt sich die Notes des letzten Laufs in
`.git/`, druckt nur Neues, zählt das Unterdrückte, `--all-notes` zeigt
alles; ein frischer Checkout hat kein Ledger und druckt alles — CI erbt
kein lokales Schweigen) und **`finish.py --apply`** (der Tail-Checker
führt den deterministischen Teil selbst aus statt ihn zum Abtippen zu
drucken: Archiv-Commit und Rebase immer, Merge/Push/Branch-Löschen nur
hinter der vollen Suite des Pakets — `--tests CMD` läuft sie, `--tests-
passed` behauptet sie; jeder Schritt druckt sein Kommando, der erste
Fehler stoppt in einem Zustand, den git erklärt), `v2.8.1`.

SP66 (token-savers, die restlichen drei Kandidaten aus derselben Frage:
**Kontextkosten messen** (`process_context.py --cost`: was ein Session-Start
lädt, gruppiert nach Anker, Commands, Prozessdokus, Produktrahmen, aktive
Pläne, State/Journal, alle Journal-Shards, Spec-Verzeichnisse, mit
Session-Start-Schätzung und den zehn größten Dateien — chars/4, also
vergleichbar untereinander, nicht mit der Rechnung; erst messen, dann
kürzen), **Journal-Kompaktion** (`compact_journal.py`: Shards älter als N
Wochen werden in ein Monatsarchiv gefaltet, das exakt die maschinell
gelesenen Records — REVIEW, GRADE — wörtlich behält und die Prosa an git
abgibt; Gates und trace globben das Archiv wie jeden Shard, gefenzte
Zitate fallen mit der Prosa weg; Dry-Run per Default) und
**Template-Update mit Owner-Liste** (`template_update.py` + `.process-owned`:
copier update wie gehabt, die Owner-Dateien bleiben wie committet, und das
Template-eigene Delta je Owner-Datei — alter Release-Render gegen neuen —
landet als Diff unter `.process-work/template-delta/<ref>/`; aus der
Stunde Hand-Konfliktlösung pro Release, gemessen am Referenzprojekt mit
fünf Skripten, einem Doc und einem Command, wird ein mechanischer Port))
ausgeliefert, `v2.9.0`.

Erster echter Lauf von `template_update.py` am Referenzprojekt deckte einen
Copier-Fallstrick auf: `modules` und `harnesses` sind abgeleitete
(`when: false`) Antworten, die copier bei jedem Update aus dem Default
neu berechnet — die aufgezeichnete Antwort gewinnt NICHT, ein abgeschaltetes
Modul kommt still zurück (beobachtet: git-hooks samt Anker-Konflikt). Der
Helfer setzt jetzt jede aufgezeichnete Antwort als `--data` neu; BOOTSTRAP
korrigiert die frühere Behauptung „recorded modules dict wins", `v2.9.1`.

Zertifikate sind nach dem verschlüsselt, was sie bezeugen (Befund im Referenzprojekt:
parallele Worktrees zerhauten sich mit einer Slot-Datei „der zertifizierte
Baum" gegenseitig die Zertifizierung — ein Eintrag je Tree-Hash, nie ein
einzelner Slot; Zwischendateien pro Lauf per mktemp, nie ein fester
geteilter Pfad; testing.md), `v2.9.2`.

Drei Befunde einer Worker-Session generisch geschlossen (Hook-Doktor prüft auch
das andere Manager-Modell: ein befülltes `.githooks/` ohne passendes
`core.hooksPath` ist hart — auf einem Worker-Host lief monatelang eine Juni-Kopie
aus `.git/hooks`; REST-Fallback in `publish_and_prune`, wenn `gh issue
comment` am GraphQL-Sekundärlimit scheitert; `.publish-denylist` — Regexes,
die beide Publish-Skripte prüfen, bevor etwas das Repo verlässt), `v2.9.3`.

Test-Lanes sind eine geteilte Ressource (Befund im Referenzprojekt: vier Agenten in vier
Worktrees ließen ihre gescopten Suiten gleichzeitig laufen, Load 6, alles
kroch — und ein kriechendes Gate wird umgangen; testing.md: Zertifikats-
Transfer am Push und eine flock-Spur je Host — anstellen statt drosseln,
kein Bypass), `v2.9.4`.

SP67 (ui-evidence, auf die Maintainer-Frage „sind Screenshots zum Abgleich und zur
Erfolgskontrolle hinterlegt?" — sie waren Beweis an der Untergrenze, aber
kein Abgleich mit der Absicht und für den Owner unsichtbar: **DoD D8**
(Vorher-Nachher-Paar je Viewport, Theme und Zustand unter
`.process-work/reviews/<slug>/`, aus dem Review-Report verlinkt; das
Nachher-Bild wird gegen die Absicht beurteilt, nicht nur gegen die
Untergrenze); **Review-Bundle „UI evidence"** (listet das Paar und jedes
Bild, das der Diff berührt — fehlendes Paar ist Befund, kein Skip; /review
und Checkliste verlangen das Urteil „entspricht der Absicht"); **Digest
Sektion 6** (was sich auf dem Bildschirm geändert hat: Evidenzpaare und
geänderte Pixel-Baselines als Pfade zum Öffnen);
**check_baseline_duplicates.py** (byte-identische Screenshots unter
verschiedenen Namen sind Beweis für nichts — Ratchet mit Baseline-Pin;
erster Lauf am Referenzprojekt: 16 Gruppen, darunter „Fehler" identisch mit
„teilweise geladen")) ausgeliefert, `v2.10.0`. Patch: das Evidenz-Verzeichnis
eines Spec-Kit-Plans (`specs/NNN-x/plan.md`) wird über das Verzeichnis
gefunden, nicht über den Dateinamen `plan`, `v2.10.1`.

SP68 (residue, auf die Maintainer-Frage „räumt der Prozess ausreichend auf?" — gemessen
am Referenzprojekt: 353 von 457 Remote-Branches bereits gemergt, 9 von 35 Spec-
Verzeichnissen fertig, 5 aktive Pläne älter als zwei Wochen, alles ohne
Rhythmus; nur die Plan-Archiv-Retention funktionierte, weil sie hart im Hook
sitzt und der Fix ein Kommando ist: **`tidy.py`** (ein Report je Altlast mit
dem Kommando, `--apply` erledigt den sicheren Teil — gemergte Remote-
Branches, fertige Spec-Verzeichnisse via publish_and_prune, Journal falten,
alte Archive, template-delta; alte aktive Pläne und stille Issues nur
gelistet: Owner-Entscheidung) und **Digest Sektion 7** (dieselben Zahlen
jede Woche vor dem Owner)) ausgeliefert, `v2.11.0`.

SP69 (dialogue-decisions, Maintainer-Befund aus einem zweiten Prozess-Einsatz:
Entscheidungen im Dialog landen nicht im Plan und gehen beim Kompaktieren
verloren — der Kernel schützt sich selbst, Entscheidungen nicht: **`##
Decisions`-Ledger im Plan** (eine `DECISION <Datum> <wer>: <was> — because
<warum>`-Zeile je Entscheidung, geschrieben vor dem nächsten Schritt;
Plan-, Execute- und Prime-Command sowie workflow.md tragen die Pflicht),
**Re-Hydration liest sie** (process_context.py gibt das Ledger je aktivem
Plan aus — /prime, /execute, /review sehen es nach jeder Kompaktierung
wieder; die Kernel-Direktive nennt den Abschnitt, byte-identisch in allen
vier Kopien) und **sichtbare Lücke** (Review-Gate-Note für Tier-2+-Pläne
ohne den Abschnitt, auch specs/*/plan.md — das Gate kennt keine fehlende
Entscheidung, aber ein Reviewer fragt bei leerem Ledger nach)) ausgeliefert,
`v2.12.0`.

SP70 (computed-evidence, Maintainer-Befund aus einem zweiten Einsatz: 15 von 16
Review-Digests wurden nie berechnet — plausibles Hex, das kein Byte-Strom
irgendeines Commits erzeugt; das Gate meldete es bei jedem Lauf, bis es
als Dauerrot niemand mehr las. Zwei Antworten: **Evidenz wird berechnet,
nie getippt** (`attest.py` schreibt die REVIEW-Zeile: Digest aus base/head
mit der Formel des Gates neu gerechnet, veraltetes Bundle verweigert,
Grammatik geprüft, an den Tagesshard angehängt; die Formel ist EIN Owner
in check_review — `CANONICAL_DIFF` pinnt jede git-Config-Stellschraube
(algorithm, renames, prefix, abbrev, ext-diff, textconv), damit ein Digest
auf jedem Klon gleich verifiziert; Legacy-Digests bleiben gültig; ein Wert,
den keine Formel erzeugt, heißt im Gate jetzt FABRICATED und zählt als
fehlendes Review) und **Dauerrot bekommt ein Alter** (gate_runner merkt sich
je Gate den ersten roten Tag in `.git/` und druckt das Alter mit jedem
Fehlschlag; Digest Sektion 8 zeigt es dem Owner); dazu **Abschalten durch
Weglassen geschlossen** (dritter Maintainer-Befund: zwei Pläne ohne `tier:`-Zeile
waren für jedes Gate unsichtbar, bis sie eine bekamen und sofort zwei
Pflichten scharf wurden — ein aktiver Plan und ein specs/*/plan.md ohne
Tier sind jetzt hart, archivierte bleiben Note)) ausgeliefert, `v2.13.0`.

Drei Befunde einer Worker-Session generisch geschlossen:
**Hook-Doktor für `.githooks/`** (ein getracktes Hook-Verzeichnis ohne
passendes `core.hooksPath` liest git nie — im Referenzprojekt lief monatelang
eine Juni-Kopie von pre-push aus `.git/hooks`, und ein geleaktes GIT_DIR
schaltete darüber das echte Repo auf `core.bare=true`; hart im gate_runner
und in finish), **REST-Fallback beim Posten** (`gh issue comment` läuft
über GraphQL, dessen Sekundärlimit stundenlang blockte, während das
REST-Budget unberührt war — publish_and_prune fällt auf
`gh api …/comments` zurück, Verifikation liest zuerst per REST) und
**Deny-Liste vor dem Veröffentlichen** (`.publish-denylist`, projekteigene
Regexes; ein Treffer verweigert den Post und nennt die Zeile —
publish_and_prune und publish_review.sh; Anlass: projektinterne Bezeichner
in einem Spec-Snapshot), `v2.9.3`.

SP71 (design-contracts, generalisiert aus der Praxis im Referenzprojekt für Web
und App: UI-Arbeit scheiterte wiederholt daran, dass jeder Agent etwas
Plausibles rendert und niemand sagen kann, welches Bild *richtig* war —
im Referenzprojekt geheilt durch je Surface einen Designvertrag mit stabilen IDs,
gesiegelte Render-Runden als Referenz, unabhängiges Review mit GO und
Amend-before-Code. Der Template macht daraus ein Modul im Standard-Set,
inert bis zum ersten Registry-Eintrag: **Registry** (`docs/process/
design-contracts/<surface>.json`: Vertrag, Status draft/accepted,
sha256-Pin, ID-Familien, ADR, Review, gesiegelte Referenz, Code-Pfade),
**Gate** (`check_design_contracts.py` — hart: Pin-Drift ohne Re-Pin,
doppelt definierte ID, accepted ohne ADR oder ohne Review mit
`Decision: GO`, Review mit anderem Siegel als die Referenz, Referenz mit
gebrochenem Siegel, aktiver Plan zitiert eine ID, die der Vertrag nicht
kennt; Note: opaker Pin, Draft, Boards aus älterem Vertrag, Surface-Push
ohne zitierte ID), **`seal.py`** (Manifest + sha256 über Rundenordner und
deklarierte Abhängigkeiten, `--verify` schlägt auf editierte, fehlende
und undeklarierte Dateien fehl, Drift einer Abhängigkeit ist Exit 2),
**Vorlagen** (Vertragsgerüst mit §-Blöcken und Amendment-Log,
Review-Vorlage mit Rubrik/GO/Siegel-Hash, Runden-README mit Ablauf)
und **Bindung ohne neue Kettenglieder** (R5 nennt jetzt auch die
Vertrags-IDs, D8 beurteilt das AFTER-Bild gegen das gesiegelte Board
der zitierten IDs, Review-Checkliste Surfaces und Regel 3 entsprechend;
das Review-Bundle nennt den regierenden Vertrag und die zitierten IDs).
Die Gestaltung selbst bleibt Menschen- und Reviewer-Urteil gegen die
Boards; Render-Kit, Export-QA und Token-Lints bleiben projektspezifisch,
das Modul beschreibt nur das Muster) ausgeliefert, `v2.14.0`.

**Siegel-Interop** (`seal.py --verify` und das design-contracts-Gate lesen
auch das Manifest eines projekteigenen Render-Kit-Freezers: `files` als
Liste `{path, sha256}`, Abhängigkeiten als `externalDependencies` mit
ordnerrelativen `../..`-Pfaden, `manifest.sha256` in sha256sum-Form
`<hex>  manifest.json` — dieselbe Formel, ein Verifizierer; Anlass: drei
bereits gesiegelte Runden im Referenzprojekt), `v2.14.1`.

**Plan-Bindung** (erster Lauf im Referenzprojekt: ID-Familien sind
surface-übergreifend — E1 ist auf Web wie in der App eine Ebene —, ein App-Plan
wurde gegen den Web-Vertrag geprüft und `C8` galt nicht als `C08`. Ein
Plan wird nur gegen den Vertrag geprüft, den er nennt (Pfad oder
`design-contract: <surface>`-Zeile); ein Plan mit Familien-IDs ohne
Nennung bekommt genau eine Note; Nullen sind keine Identität), `v2.14.2`.

**Integritäts-Ledger im Review-Gate** (Befund im Referenzprojekt: 628
digest-gebundene REVIEW-Zeilen, je Zeile mehrere git-diffs, eine
kanonische Diff großer Spannen ~3 s — der pre-push-Gate wurde nie
fertig. Die Eingaben einer Verifikation sind im Klon unveränderlich,
also auch ihr Ergebnis: ein einmal geprüfter Record wird in
`.git/process-review-integrity` gemerkt — „ok" wie Mismatch, ein
erfundener Digest bleibt bei jedem Lauf rot, ohne neu gerechnet zu
werden; Shards, die der Push selbst ändert, werden immer frisch
geprüft; fehlende Commits werden jedes Mal neu gesucht.
`--full`/`PROCESS_REVIEW_INTEGRITY=all` prüft alles, `=in-flight` nur
die geänderten Shards (CI-Schalter für riesige Journale)), `v2.14.3`.

**Kein Push wartet blind** (Befund 2026-09-18 im Referenzprojekt: der
pre-push-Hook stand hinter einem Volllauf an, der Tool-Call des Agenten
starb nach 40 Minuten bei 96 % der Scoped-Tests, fünfmal hintereinander.
Regel in git-hooks.md und /finish: ein Hook, der Minuten laufen kann,
wartet begrenzt und bricht mit Halter und Ausweg ab; die Evidenz entsteht
entkoppelt im Hintergrund (Certify-Schritt, Baum-Zertifikat), der Push
liest sie. Werkzeug bleibt projektspezifisch — im Referenzprojekt
ein Lane-Skript mit zwei Lanes und ein Certify-Ziel),
`v2.14.4`.

SP72 (tower — der deterministische Kern eines Steuermanns für parallele
Arbeit: die Idee des Maintainers eines Agenten, der viele Worker koordiniert, mit ihm
spricht, Probleme findet und Ressourcen steuert. Bevor ein Agent urteilt,
braucht er eine Lage, die nicht erzählt, sondern berechnet ist:
**`tower.py`** (eine Tabelle aus Zustand, den der Prozess schon führt —
alle Worktrees des Klons mit Vorsprung/Rückstand, Pfaden in Flug, Dirty-
Zahl und Minuten seit dem letzten Commit; **Überlappungen** zweier
Worktrees auf derselben Datei (hoch) oder demselben Verzeichnis (niedrig);
aktive Pläne mit Tier, Issue, Decisions-Zahl, design-contract-Bindung;
Reviews des Tages; rote Gates mit Alter; Lanes, wo es sie gibt; Worker-
Meldungen) und **deterministische Befunde mit Begründung** (Überlappung,
Tier-2+-Plan ohne Issue, Plan ohne Decisions-Ledger, Plan ohne Tier,
chronisch rotes Gate, stiller Worker ohne Commit und Meldung seit einer
Stunde, blockierter Worker, Branch weit hinter main; `--json`,
`--min-severity`, `--stale-minutes`); **Worker-Protokoll** (`/report`,
`report.py`: planned/pushed/review-pass/blocked/done/idle, eine Zeile je
Zustandswechsel in das gemeinsame Git-Common-Dir des Klons, nie
committed). Der Tower entscheidet nichts und redet mit niemandem — er ist
die Eingabe des Steuermanns, damit dessen Tokens in Urteil fließen
(zuteilen, umlenken, beenden) und nicht in Nachfragen bei dreizehn
Workern; Doku `docs/process/tower.md`) ausgeliefert, `v2.15.0`.

SP73 (train + steward — Maintainer-Wunsch: Aufträge sammeln und zu einem
günstigen Zeitpunkt effizient mergen und deployen, statt dass dreizehn
Agenten dreizehn Volläufe und Deploys zahlen. **Merge-Zug** (`train.py`:
`plan` zeigt, wer einsteigen darf und warum nicht — berechnet, nie
behauptet: archivierter Plan auf dem Branch mit klärendem REVIEW-Pass
oder Waiver, Worker-Meldung nur als Zeiger, nie als Ersatz für einen
fehlenden Pass; keine Datei-Überlappung mit einem bereits eingestiegenen
Branch; kein rotes Gate; Abfahrt bei `--min-candidates` oder
`--max-wait-hours`, nur bei freien Lanes, `--force` fährt sofort. `run`:
Staging-Branch aus main im eigenen Worktree, Kandidaten in
Wartereihenfolge gemerged (Konflikt = aussteigen), Prozess-Gates und die
volle Suite EINMAL auf dem kombinierten Baum; bei Rot findet eine
Präfix-Bisektion den ersten Verursacher, er steigt aus und wird
`blocked` gemeldet; bei Grün Fast-forward von main, `--push`, Branches
gelöscht, `done` je Worker, `--deploy` einmal) und **Steward-Rolle**
(`/steward`: Tower lesen statt Sessions befragen, Befunde nach Schwere
abarbeiten, zuteilen, umlenken, nur eigene Kinder stoppen und nur nach
committed Plan und Decisions, Zug abfertigen, dem Owner nur bei
Ereignis schreiben; nie implementieren, reviewen, zertifizieren;
Modellwahl nach Tier, Budget je Issue); Doku `docs/process/train.md`)
ausgeliefert, `v2.16.0`.

**Zugplan ohne Reste** (erster Lauf im Referenzprojekt: 350 bereits
gemergte Branches erschienen als „nothing ahead" — Rückstände sind
Sache von `tidy.py`, keine Kandidaten; der Plan zeigt nur Branches mit
Vorsprung), `v2.16.1`.

**Tower über Hosts hinweg** (Maintainer-Anforderung: der Prozess bleibt
host-agnostisch — im Referenzprojekt läuft die Steuerung auf einem
Host, ein abgesetzter Worker auf einem zweiten. Der einzige Kanal, den jeder
Host schon hat, ist git, also ist er der Transport: `report.py --sync`
(oder `PROCESS_REPORT_SYNC=1`) veröffentlicht die Meldungen eines Hosts
als Blob unter `refs/process/reports/<host>` auf origin — kein ssh,
nichts auf einem Branch committed; `tower.py --remote` (oder
`PROCESS_TOWER_REMOTE=1`) holt origin und diese Refs: Branches anderer
Hosts erscheinen als `elsewhere` mit Vorsprung, Pfaden in Flug und Alter,
nehmen an der Überlappungsprüfung teil und können stale sein wie ein
lokaler Worker; die Meldungen aller Hosts werden zusammengeführt, je
Worker gewinnt die jüngste. Starten und Stoppen auf dem anderen Host
bleibt dessen Mechanismus; die Steward-Regel ändert sich nicht), `v2.17.0`.

**Rückstand ist kein Flug** (erster Remote-Lauf im Referenzprojekt:
Juli-Branches, tausende Commits hinter main, erschienen als „anderswo in
Flug". Ein Branch ohne Commit seit 14 Tagen wird gezählt statt gelistet
und als ein Befund `remote-residue` gemeldet), `v2.17.1`.

**Anleitung verdrahtet** (Maintainer-Frage „ist die Anleitung angepasst?" —
nein, war sie nicht: Tower, Report, Zug und Steward standen nur in ihren
eigenen Docs. Jetzt: workflow.md „Parallel agents" erklärt die vier und
sagt ausdrücklich, dass ohne Steward jede Session autonom bleibt — Gates
und /finish tragen weiter, der Tower macht nur sichtbar, der Zug nur
billiger; /plan, /execute, /review und /finish nennen ihren
`/report`-Zustandswechsel und der Zug den Weg am /finish-Merge vorbei;
README-Commands-Liste), **Steward hält das Repo sauber und die Issues
geschlossen** (Housekeeping-Abschnitt: täglich `tidy.py --apply` für
den sicheren Teil, Owner-Frage für das, was tidy nur listet,
`remote-residue` aus dem Tower; Issues-Abschnitt: Worker besitzen ihre
Claims und Closes, der Steward schließt Nachzügler mit dem Merge-Ref,
macht Befunde zu getypten Issues, gibt tote Claims nach zwei Stunden
frei; der Zug druckt je gemergtem Branch die referenzierten Issues),
`v2.17.2`.

**Unabhängiges Review von Tower, Zug, Report, Designvertrag und Ledger**
(Maintainer: „check nochmal alles durch, ohne Bias" — ein frischer Reviewer ohne
Kontext fand 26 Befunde, sechs davon hoch; alle mit Repro. Behoben:
Zug — Tier aus dem Roh-Text las eingezäunte Beispiele als Deklaration
(jetzt `_unfenced` wie im Review-Gate), ein de-datierter Slug ließ einen
Januar-Pass einen September-Plan gleichen Namens klären (jetzt die
Eindeutigkeitsregel des Gates), Push nach origin ohne Vorfahren-Prüfung
konnte ein main ohne lokale Commits veröffentlichen (jetzt Abbruch),
ein gescheitertes lokales `branch -d` löschte trotzdem auf origin (jetzt
gekoppelt und gemeldet), die Bisektion beschuldigte bei rotem main den
ersten Kandidaten (jetzt Basis-Check: rotes main beschuldigt niemanden),
Konflikt-Aussteiger blieben stumm (jetzt `blocked`-Meldung); Tower — main
und `.process-work/` erzeugten Überlappungs-Befunde, ein README zählte als
Plan, ein lokal anders benannter Branch überlappte mit sich selbst auf
origin, ein fehlgeschlagener Fetch war unsichtbar (jetzt Befund
`remote-unreachable`, kein `--prune`); Report — Hostnamen wurden am
ersten Punkt gekappt (`build.eu`/`build.us` teilten einen Ref), Timeouts
ungefangen; Designvertrag — `Decision: GO/NO-GO meeting` galt als GO,
eingezäunte Beispiele zählten, jede 64-Hex-Zahl im Review galt als
Siegel (jetzt nur eine benannte `manifest.sha256:`-Zeile), eine
Unterüberschrift mit ID zählte als zweite Definition; Siegel — ein
verschachteltes `manifest.json` war vom Siegel ausgenommen; Ledger —
`--full` prüfte neu, schrieb aber nicht zurück, ein vergifteter Eintrag
überlebte (jetzt baut `--full` den Ledger neu). Doku an den Code
angeglichen, Bedrohungsmodell des Towers ehrlich benannt), `v2.17.3`.

SP74 (dispatch + Modell-Policy — Maintainer-Frage „startet das System die
Sessions selbst?" (nein, bis jetzt) und „je Phase ein anderes LLM?" (ja,
weil die Phasen über Artefakte getrennt sind: Plan und Decisions-Ledger,
dann das Bundle). **`docs/process/model-policy.json`** ist die eine
Stelle, an der man dreht: Tier × Phase → Modell, dazu der projekteigene
Startbefehl als Vorlage (`{model}`, `{prompt}` — der Prompt ist EIN
Argument, nie durch eine Shell) und `max_workers`; projekteigen, gehört
in `.process-owned`. **`dispatch.py`** startet je Phase eine abgesetzte
Session im Worktree des Branches (`start --issue N --phase
plan|execute|review`, findet den Branch des Issues wieder), führt Buch in
`.git/process-dispatch/`, zeigt Liveness (`list`), stoppt nur eigene
Kinder und nur bei committetem Baum (`stop`, `--force`), weigert sich
bei erreichtem `max_workers` oder gehaltener Lane. **Messen statt
Bauchgefühl:** `report.py --model` (oder `PROCESS_MODEL`/`PROCESS_PHASE`
aus dispatch) hält fest, welches Modell welche Phase fuhr;
`process_kpis.py models` (Telemetrie) schneidet Review-Runden bis zum
Pass und Blocks nach Tier × Phase × Modell — ehrlich als Proxy mit
Konfidenz, die Zahl, an der die Policy gemessen wird. `/steward` teilt
über dispatch zu und ändert Modelle nur über die Policy-Datei)
ausgeliefert, `v2.18.0`.

SP75 (sichtbare Worker und ein Frageprotokoll — Maintainer-Erfahrung mit dem
ersten Steward: „ich sehe zu wenig, Fragen kommen spät und ohne Kontext".
Zwei Entwurfslücken, geschlossen: **Worker als tmux-Fenster** (Policy
`runner: tmux`, `tmux_session`; `dispatch.py` öffnet je Worker ein
Fenster einer tmux-Session — interaktiv, vom Menschen zu öffnen, Ausgabe
per pipe-pane ins Log, Start als Shell → Pipe → send-keys, damit die
erste Sekunde nicht verloren geht und die TUI ihr tty behält;
`dispatch.py log <branch>`; der Tower führt `sessions` mit letzter
Ausgabezeile und Alter je Worker), **Frageprotokoll** (eine Frage an den
Owner ist eine Zeile im Plan: `DECISION NEEDED <Datum> <Worker>: <Frage>
— options: …; recommendation: …` plus `blocked`; der Tower führt
`questions` und meldet sie als hohen Befund; die Antwort wird als
`DECISION`-Zeile zurückgeschrieben, der Worker liest den Plan; Notizen
bis 1000 Zeichen) und **Steward wacht statt zu ticken** (Dateiwache auf
Meldungen und Pläne, Takt nur als Rückfallebene; Fragen werden
vollständig und sofort durchgereicht — Issue, Branch, Frage, Optionen,
Empfehlung, Lage), `v2.19.0`.

**Zweites unabhängiges Review (v2.18/v2.19) — 19 Befunde eingearbeitet.**
Ein frischer Reviewer las Dispatch, Tower, Train, Steward und
Modellpolitik ohne Vorwissen. Die harten Befunde: tmux-Worker galten
ewig als lebendig (die Shell-PID war nicht der Worker); `stop` konnte
fremde Prozesse treffen (recycelte PID, PID 0 = eigene Gruppe); ein
fremdes Verzeichnis am Worktree-Pfad wurde als Worktree akzeptiert;
Fragen im Worktree eines Workers sah der Tower nicht (er las nur den
eigenen); die Modell-KPIs zählten Runden je Meldung statt je Issue; der
Prompt lief trotz Doku durch eine interaktive Shell; der Steward hatte
Anweisungen ohne Mechanismus („Dateiwache", „Nachricht ins Fenster").
Geschlossen: `dispatch.py` neu — Lebendigkeit ist der Pane-Zustand
(`pane_dead`, `remain-on-exit`), nie eine Shell-PID; Records tragen PID
plus Startzeit, `stop` beendet nur den aufgezeichneten Prozess; das
Fenster läuft eine nicht-interaktive `sh` mit exakter POSIX-Quotierung
und `exec`; `{model}`/`{prompt}` werden auch innerhalb eines Tokens
ersetzt; `CLAUDECODE`/`CLAUDE_CODE_*` werden für beide Runner entfernt;
`issues.json` findet den Branch eines Issues auch nach einem Stop; der
Prompt beginnt mit dem Slash-Befehl und trägt das Frageprotokoll; neu
`dispatch.py say <branch> "<Text>"` tippt eine Zeile in einen
tmux-Worker; `log` zeigt bei tmux den Bildschirm (ein TUI-Log ist
Escape-Codes), sonst den Log-Schwanz ohne ANSI; die Dirty-Prüfung zählt
Untracked mit. Tower: `questions` liest jeden Worktree dieses Klons und
per `git show` die Branches anderer Hosts (`--remote`); die Fragezeile
verträgt Fettdruck und fehlendes „wer"; `sessions` zeigt den Zustand
(live/dead/gone/unknown). Train: ein offener `DECISION NEEDED` hält den
Branch vom Zug. `process_context.py` führt `open_questions` je Plan
(/prime sieht, worauf gewartet wird). KPI `models`: ein Issue ist eine
Einheit, das zuletzt gemeldete Modell je Phase besitzt sie, Runden einmal
je Issue. Steward-Anleitung ohne Erfindungen: Takt per `/loop`, keine
Dateiwache im Prozess; Antworten per `say` an den fragenden Worker, nie
zwei Schreiber auf einem Plan; Trust-Grenze der Policy (`command` läuft
auf dem Steward-Host — wie CI-Konfiguration zu prüfen) in `tower.md` und
der Policy selbst; Hinweis auf Berechtigungen (`-p` braucht eine
Freigabe, interaktiv ggf. Trust-Dialog), `v2.19.1`.

**Fragen als Menü.** Der Steward reicht eine Worker-Frage nicht mehr als
Absatz durch, sondern als Auswahl: wo die Harness ein Frage-Werkzeug hat
(Claude Code: `AskUserQuestion`), eine Frage je Worker mit den Optionen
des Workers als anklickbare Antworten, die Empfehlung zuerst und als
„(Recommended)" markiert, Issue/Branch/Lage im Fragetext; ohne Werkzeug
eine nummerierte Liste; bis zu vier offene Fragen in einem Aufruf,
älteste zuerst. Funktioniert in der App und per Remote Control,
`v2.19.2`.

**Re-Hydrierung als Mechanismus, nicht als Satz.** Bisher stand nur im
Kernel „nach einer Kompaktierung lies Kernel, Regeln und Ledger neu" —
ein Satz, der die Kompaktierung überleben muss, vor der er warnt; dem
Owner fiel auf, dass Worker das nicht tun. Neu `scripts/process/rehydrate.py`:
druckt, was `/prime` liest, und nichts mehr (Kernel-Block, Pflichtregeln,
aktive Pläne mit Tier/Issue, DECISION-Ledger, offene DECISION-NEEDED-Fragen
mit dem Hinweis „nicht selbst entscheiden", nächste Aufgabe, State-File,
Journal-Shard) — als Claude-Code-`SessionStart`-Hook für `compact|resume`.
`rehydrate.py --install` trägt den Hook idempotent in `.claude/settings.json`
ein, ohne den Rest der Datei anzufassen (sie bleibt Projekteigentum);
`--check` sagt, ob er da ist. `/prime` bleibt für die Fälle, die der Hook
nicht abdeckt; `start-here.md` beschreibt den Mechanismus. Dazu ersetzt
`dispatch.py` im `command` der Policy auch `{branch}` und `{issue}`, damit
eine Harness die Sitzung benennen kann — Claude Code: `--remote-control={branch}`
macht jeden Worker in der Claude-App sichtbar (die `=`-Form, sonst frisst
der optionale Name des Flags den Prompt), `v2.20.0`.

**Subagenten im Worker: Lesen auslagern, nie die Änderung.** `/execute`
sagt jetzt, wofür ein Worker Subagenten nutzt — Suche über die Codebasis,
Diagnose aus langen Testläufen, Doku-Abgleich: viel lesen, wenig
zurückgeben — und wofür nicht: die Änderung selbst, weil der Subagent
weder Kernel noch Ledger kennt und der Worker einen Commit signiert, den
er nicht gesehen hat (Regel 1); Ausnahme bleibt das `[P]`-Protokoll.
Dazu `rehydrate.py --install` behält die Escapes der Settings-Datei bei,
`v2.20.1`.

**Aus dem ersten Steward-Tag.** Zwei Befunde des Owners, beide aus dem
Betrieb: (1) Der Steward ließ einen Worker eine Stunde auf `planned`
warten, weil er nur alle 30 Minuten tickte und gerade eine Frage
durchreichte. Die Anleitung kannte keine Wache — Claude Code hat aber
eine: `Monitor` auf `tail -f` der Reports-Datei weckt beim nächsten
`planned`/`pushed`/`blocked`/`review-pass`/`done` sofort; sie lebt maximal
30 Minuten und wird bei jedem Wecken neu gestellt, der `/loop`-Takt bleibt
Rückfallebene (ein `DECISION NEEDED` ohne `blocked` sieht nur der Tower).
Phasenwechsel warten auf niemanden: nach `planned` sofort `execute`, nach
`pushed` sofort `review`; der Owner wird informiert, nicht gefragt.
(2) Ein Gate war im Zug rot, im Root nicht reproduzierbar: der
Staging-Worktree lag unter `.git/process-train/`, und ein Dateilister,
der jeden Pfad mit `.git`-Segment überspringt, sah einen leeren Baum.
Der Staging-Worktree liegt jetzt als Geschwister neben dem Root
(`<root>-train`, wie die Dispatch-Worktrees), nur Logs bleiben im git
common dir, `v2.21.0`.

**Phasen auf einem anderen Host.** Der Steward im Referenzprojekt stellte fest: der
Engpass ist die CPU des Steuer-Hosts, nicht die Zahl der Plätze; Reviews binden
viel davon und brauchen nur git. Die Policy kennt jetzt `phases.<phase>`
mit `command`, `runner` und `remote: true`: ein Remote-Phase-Start legt
keinen Worktree an, der Befehl ist die Übergabe (Cloud-Sitzung, ssh),
der Branch muss auf origin liegen, der Prompt weist den Worker an, mit
`--sync` unter eigenem `PROCESS_HOST` zu melden; `list` zeigt REMOTE,
`stop` vergisst nur den Record, `tower.py --remote` sieht die Meldungen.
`tower.md` sagt, warum Reviews zuerst wandern (git-only, CPU-schwer, und
ein frischer Klon auf einem anderen Host ist Unabhängigkeit) und dass ein
Push von dort keinen lokalen Pre-Push-Hook durchläuft. Dazu:
`rehydrate.py` druckt nur die letzten zwölf Entscheidungen eines Plans
(ein Plan mit 113 DECISION-Zeilen ist ein Log, jede Kompaktierung zahlte
ihn), `v2.22.0`.

`dispatch.py` wertet die Lane-Sperre jetzt nach Lane und Phase aus statt
pauschal: `lane.py status` wird zeilenweise gelesen, ein gehaltenes `full`
sperrt nur `execute` (Plan und Review laufen unter dem Zug), ein
gehaltenes `scoped` oder eine unbekannte Lane sperrt alles. Eine
Remote-Phase sieht weder `max_workers` noch Lane, denn ihre Last liegt auf
dem anderen Host. `--dry-run` nennt die Regel, die erlaubt oder verweigert
hat, und behält bei Verweigerung Exit 3; `tower.md` und der Docstring
sagen dasselbe, `v2.23.0`.

**Dokumentation als Einstieg, ohne Template-Änderung.** `docs/UEBERBLICK.md`
(und inhaltsgleich als PDF) erklärt den Prozess in elf Kapiteln und ist der
neue Einstieg aus dem README. BOOTSTRAP nennt die fünf tatsächlichen Fragen,
empfiehlt für Updates `template_update.py` statt eines Beispiel-Dictionaries,
das Module abgeschaltet hätte, und erklärt parallele Agenten (Modellpolitik,
`rehydrate.py --install`, Steward, Dispatch, Zug); beides an einem frischen
Headless-Render nachgeprüft. SYSTEM-REQUIREMENTS ohne GitLab und `parity`,
mit tmux und den Koordinationsskripten. Das öffentliche Repo nennt das
Ursprungsprojekt nur noch als Referenzprojekt und enthält keine Betriebsdetails,
Klientenbezüge oder Vornamen mehr; die Neutralitätslisten der Tests bleiben.

**Lizenztext im gerenderten Repo, SBOM erzeugt statt gepflegt.** Jedes
eingerichtete Repository erhält `docs/process/LICENSE` (Apache 2.0, identisch
mit dem Repo-`LICENSE`, ein Test hält beide gleich) und `docs/process/NOTICE.md`:
Die Lizenz gilt für die gerenderten Prozessdateien, nicht für Code und Inhalt
des Projekts; geänderte Prozessdateien tragen einen Änderungshinweis. Bisher
lieferte das Template den Lizenztext nicht mit, obwohl Apache 2.0 ihn bei
Weitergabe verlangt. Die Repo-SBOM war von Hand gepflegt und stand auf
v1.37.0; `tools/gen_sbom.py` erzeugt jetzt `docs/SBOM.md` und
`docs/sbom.cdx.json` (CycloneDX 1.5, mit Hashes und Abhängigkeitsgraph,
deterministisch) aus `pyproject.toml` und `uv.lock`, und `test_sbom.py` lässt
CI rot werden, sobald eine der beiden Dateien veraltet.

**`pushed` wird geprüft, nicht geglaubt.** Im Referenzprojekt meldeten
Worker an einem Tag dreimal `pushed`, bevor die Arbeit auf origin lag; der
Steward startete daraufhin die nächste Phase auf einem Branch ohne diese
Arbeit. `report.py pushed` verweigert jetzt, solange der Branch nicht mit dem
HEAD des Worktrees auf origin liegt oder origin seit Phasenstart keinen neuen
Commit hat; `dispatch.py` gibt den Startpunkt als `PROCESS_PHASE_BASE` mit.
`--force` bleibt für ein unerreichbares origin und markiert die Meldung als
unverifiziert.

**Greenfield-Prüfung durch einen unabhängigen Agenten** (leeres Repo, alle
Harnesses, `regulated`, Hooks, Spec Kit, ein Tier-2-Durchlauf): kein Blocker,
behoben wurde: `template_update.py` verdoppelte bei jedem Lauf die Quotes
leerer String-Antworten (`github_repo: ''`) und erkennt jetzt eine
HEAD-Installation vor dem Lauf statt an copiers Downgrade-Fehler;
`scripts/process/.gitignore` und `.process-work/.gitignore` halten
`__pycache__/` und die Update-Deltas aus dem Worktree; das Spec-Kit-Setup
entfernt die drei Skills auch unter `.github/skills` (Copilot);
`start-here.md` nennt `speckit` und `design-contracts` im Standard-Setup;
`workflow.md` sagt, dass `/report`, `/steward` und `/finish` Claude-Code-
Commands sind und andere Harnesses die Skripte direkt aufrufen;
`rehydrate.py --check` bestätigt Erfolg, `train.py plan` ohne Commits hält
statt zu scheitern, `finish.py` nennt `publish_and_prune` nur für Änderungen
mit Spec. Dazu: README neu und schlank mit Verweis auf den Überblick, der jetzt
auch englisch vorliegt (`docs/OVERVIEW.md`), `v2.24.0`.

**Remote-Übergabe aus einem Terminal.** Im Referenzprojekt scheiterte die
Übergabe eines Reviews an eine Cloud-Sitzung: der Startbefehl lief nicht
ohne Terminal, und `dispatch.py` startete ihn ohne. Eine Remote-Phase mit
`"runner": "tmux"` startet den Übergabebefehl jetzt in einem tmux-Fenster;
`log` und `say` erreichen dieses Fenster, und `list` zeigt
`HAND-OVER FAILED (exit N)`, wenn es mit Fehler endete, statt die Phase als
laufend auszugeben, `v2.25.0`.

**Die Sitzung auf dem anderen Host hat einen Namen.** Im Piloten des
Referenzprojekts gab der Cloud-Start im Terminal nur Text aus, kein JSON;
die Sitzungskennung stand nur darin, und der Steward sah nicht, welche
Sitzung er prüfen musste. `dispatch.py` liest sie jetzt aus der Ausgabe der
Übergabe (Stdout oder Log des tmux-Fensters): per `phases.<phase>.handover_id`
(Regex, Gruppe 1) oder als erste URL. `list`, `log` und der Tower zeigen sie,
`v2.26.0`.

## Sub-Projekt-Tabelle (SP1–SP24)

Die Tabelle wurde bis SP24 gepflegt; ab SP25 trägt das Narrativ oben die
Historie allein.

| Sub-Projekt | Inhalt | Status |
|---|---|---|
| **SP1** Foundation | Kern + Adapter + copier-Init + additiver Brownfield-Drop-in | ✅ ausgeliefert |
| **SP2** Architektur-Onboarding | Architektur-Interview + Verifikation gegen echten Code | ✅ ausgeliefert |
| **SP3** Prozess-Vervollständigung (Multi-Repo/-Mensch) | feature-registry · github-issues · contracts-drift | ✅ Slices 1–3 |
| **SP4** Prozess-Vervollständigung II | git-hooks (lokale Enforcement-Säule) · contract-first (Interface-declared-first-Gate) · parity (Capability×Surface-Matrix, Gap→Issue) · security-floor (Pattern-Floor über git-getrackte Dateien) | ✅ ausgeliefert |
| **Capstone** command-adapters | Harness-native Slash-Commands (Claude / Copilot / AGENTS.md), dünn auf `docs/process/` zeigend, vom doc-drift-gate mitgeprüft — schließt das „vollständig wie das Referenzprojekt"-Programm bei `v1.0.0` | ✅ ausgeliefert |
| **SP7** ci-adapters | GitLab CI als zweiter Enforcement-Transport (`ci`-Namespace, includable Job + Root-Shim) · dokumentierte No-CI-Degradation · Install-Fallbacks ohne `uv` (pipx / venv+pip / lokaler Clone) | ✅ ausgeliefert |
| **SP8** english-canon | Alle Artefakte englisch (halbiert die Doku-Token je Session) · Kernel-Regel „Dialog in Nutzersprache" · „Wann lohnt es nicht"-Ehrlichkeit · Journal-Pflicht erst ab Tier 2 | ✅ ausgeliefert |
| **SP9** audit-fixes | Drei-Achsen-Audit: alle bestätigten False-Greens geschlossen (Manifest load-bearing, arch-Fence, unborn-main-Hook, hooksPath-Guard) · Failure-Modes mit Diagnose statt Traceback · doc-drift versteht dokument-relative Links · Doku-Drift bereinigt | ✅ ausgeliefert |
| **SP10** telemetry | Effizienz messbar (Audit-Finding, aus dem Referenzprojekt generalisiert): `GRADE`-Trace-Konvention im Journal · Gate lintet das Trace-Format (kein stiller Telemetrie-Verlust) · read-only KPI-Cockpit (`process_kpis.py`: effectiveness/convergence/suite/tempo/cost/cfr) · Grader-Kalibrier-Suite mit den drei Vertrauens-Schwellen (≥20/≥5 · 0 False-PASS · ≥90 % ≤2 Runden) | ✅ ausgeliefert |
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
