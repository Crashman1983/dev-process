# Changelog-Archiv — dev-process bis v2.28.1

Die Releases vor v2.28.2, neueste Version oben, in der Form des
[CHANGELOG](../CHANGELOG-DE.md): **Warum**, **Was sich ändert**, **Wirkung**,
**Update** und **Details**, wo die Geschichte sie nennt. Sie war als Erzählung
nach Sub-Projekten (SP1 bis SP79) geschrieben; die Details-Zeile nennt das
Sub-Projekt, wo die Geschichte eines nennt. Versionen ohne Tag tragen kein Datum.
English version: [changelog-archive.md](changelog-archive.md).

## v2.28.1 — Dringende Korrektur: jeder Push mit Historie wurde abgelehnt · 2026-09-24

**Warum.** Die in v2.27.1 eingeführte Auflösung annotierter Tags schrieb im Gate-Runner `^{{commit}}`. In einer Jinja-Vorlage ist das Jinja-Syntax und rendert zu `^`, also zum Eltern-Commit. Mit dem `git-hooks`-Modul lehnte die Prüfung des gepushten Stands damit jeden Push ab, dessen Commit einen Vorgänger hat. Der Test lief mit einem Repo aus einem einzigen Commit und sah es nicht.

**Was sich ändert.**
- Der Gate-Runner schreibt jetzt `^0` (ohne Klammern).
- Ein Test mit echter Historie und annotiertem Tag.
- Ein Wächter-Test gegen doppelte Klammern ohne Leerzeichen in Python-Vorlagen.

**Update.** Wer v2.27.1 oder v2.28.0 installiert hat und am Push scheitert: auf v2.28.1 aktualisieren.

## v2.28.0 — Review-Durchsetzung ohne CI geschärft · 2026-09-24

**Warum.** Eine Prüfung des Referenzprojekts zeigte drei Lücken, alle ohne CI unentdeckt:
- Ein Tier-2-Plan ließ sich ohne Review auf main mergen (die Pflicht griff erst beim Archivieren).
- Code nach dem Prüfvermerk blieb grün.
- Ein übersprungener Hook oder ein Merge über den Plattform-Button fiel niemandem auf.

**Was sich ändert.**
- Der Push auf main verlangt ab Tier 2 den klärenden Pass.
- Ein Pass gilt nur für den `head`, den er nennt. Später geänderter Code in den Pfaden des Pushs macht ihn beim Merge-Push und in `finish.py` ungültig (Journal und Pläne ausgenommen).
- Ein Tier-3-Plan, der noch aktiv ist, während Commits auf main sein Issue beanspruchen, macht das Gate ohne Pass oder `review-waived:` auf jedem Lauf rot.
- Aktive Pläne werden wie archivierte auch über den Kurznamen ohne Datum erkannt.
- Das Rezept für Cloud-Sitzungen installiert die Git-Hooks, denn auch dort wird gepusht.

## v2.27.1 — Befunde einer unabhängigen Funktionsprüfung von v2.27.0 behoben · 2026-09-24

**Warum.** Eine unabhängige Funktionsprüfung von v2.27.0 fand drei Fehler, die dokumentierte Wege brachen.

**Was sich ändert.**
- `no-commit-to-branch` lief auch beim Pre-Push und blockierte den Merge-Push von `finish` und dem Zug. Es läuft jetzt nur beim Commit.
- Die Prüfung des gepushten Stands verglich bei einem annotierten Tag das Tag-Objekt statt des Commits.
- Mit `ci.github=false` war doc-drift ab dem ersten Lauf rot, weil start-here ein Skript nannte, das nur mit CI gerendert wird.
- `template_update.py` hebt eine ältere Standardinstallation auf `sbom: true` (dort war `sbom: false` nur aus `regulated: false` abgeleitet).
- `check_issues` liest eine durch alte Update-Helfer vervielfachte leere Antwort als leer.
- BOOTSTRAP nennt alle Dateien, die im Brownfield ein `--skip` und danach einen Merge brauchen, und den Weg für Installationen unter v2.24.0.
- Die Lagetabelle liest Pläne aus allen Worktrees. Ein Worker-Plan ohne Issue wird jetzt gefunden.
- Das Review-Gate meldet ein beanspruchtes Issue nicht mehr als planlos, wenn ein Plan unter Tier 2 es nennt.
- Veraltete Texte zu gestrichenen Modulen sind bereinigt, `fix-streak` meldet OK, `make_review_bundle.py` und `tidy.py` kennen `--help`.
- Aus der Prüfung des Referenzprojekts: In der CI meldet die Hook-Verdrahtung nichts (dort ist der Job die Durchsetzung, lokale Hooks braucht er nicht). Ein nicht berechenbarer Review-Digest in einem flachen Klon (Standard einer Cloud-Sitzung) ist ein Hinweis statt rot.

## v2.27.0 — KISS-Pass nach Messung, neues Logo, Arbeitsdokumente entfernt · 2026-09-24

**Warum.** Ein unabhängiger Audit hat am Referenzprojekt gemessen, was trägt: Welche Gates je etwas gefunden haben, welche Module Artefakte haben, welche Skripte genutzt werden.

**Was sich ändert.**
- Gestrichen ist, was im Referenzprojekt leer oder ungenutzt war: die Module `contracts` (`contract-first`, `contracts-drift`), `arch_docs`, `github_master` (mit `gh_sync`/`gh_board`) und `security_floor`, dazu `trace.py`, `new_issue.*` und der Workflow `cleanup-branches` (ersetzt durch `tidy`).
- Die Frage `regulated` entfällt. `sbom` bleibt und gehört jetzt zum Standard-Setup, weil eine SBOM für den produktiven Einsatz zählt.
- Ein älteres Manifest, das gestrichene Module nennt, läuft weiter. `template_update.py` entfernt ihre Dateien.
- Aus dem Referenzprojekt zurückgeholt, wo es sich bewährt hat:
  - das Gate `fix-streak`: Der dritte Fix an einer Datei im Branch wird benannt (Regel 6).
  - das Gate `ac-text-drift`: Ein Akzeptanzkriterium lautet in Spec und Inventar gleich.
  - die Prüfung, dass ein Pre-Push den geprüften Stand pusht (`PRE_COMMIT_TO_REF` gegen HEAD).
  - das Attest immer in den Journal-Ordner des Branches, sodass parallele Reviews nicht mehr in einer Tagesdatei kollidieren.
  - im Zug der Gate-Start über `gate_invoke`.
  - ein zweiter Lauf bei rotem Basisstand und der Push aus dem Staging-Worktree.
  - im Delta-Bundle nur die Befunde DIESES Vorgangs und nie ein veraltetes Bundle nach einem gescheiterten Lauf.
  - eine Anleitung für den Einrichtungs-Hook von Cloud-Sitzungen (`tower.md`).
- Es gibt jetzt 15 Gates statt 16/18.
- Logo: `docs/assets/` enthält das Zeichen (`mark.svg`), die Wortmarke für helle und dunkle Flächen und ein Social-Preview-Bild (1280×640). Drei Agenten laufen auf eigenen Spuren in ein Gate aus je vier Tiers, dessen Öffnung nur eine Linie breit ist, und verlassen es als eine geprüfte Linie: ein Häkchen, das in einem Merge-Punkt endet.
- Aufgeräumt: Die Arbeitsdokumente seit Juli sind aus dem Baum entfernt. Das sind `docs/design/` und `docs/plans/` (67 Entwürfe und Pläne, die meisten aus der Zeit vor dem Lean-Pass), `docs/pilots/`, die Audit-Berichte unter `.process-work/reviews/` und `docs/CAPABILITIES.md`, das der Überblick ersetzt. Sie bleiben in der Git-Historie, dieser CHANGELOG erzählt die Entwicklung.
- Der geltende Spec-Kit-Entwurf liegt jetzt bei der Analyse unter `docs/analysis/`.

## v2.26.0 — Die Sitzung auf dem anderen Host hat einen Namen · 2026-09-24

**Warum.** Im Piloten des Referenzprojekts gab der Cloud-Start im Terminal nur Text aus, kein JSON. Die Sitzungskennung stand nur darin, und der Steward sah nicht, welche Sitzung er prüfen musste.

**Was sich ändert.**
- `dispatch.py` liest die Sitzungskennung jetzt aus der Ausgabe der Übergabe (Stdout oder Log des tmux-Fensters).
- Sie wird per `phases.<phase>.handover_id` (Regex, Gruppe 1) oder als erste URL erkannt.
- `list`, `log` und der Tower zeigen sie.

## v2.25.0 — Remote-Übergabe aus einem Terminal · 2026-09-24

**Warum.** Im Referenzprojekt scheiterte die Übergabe eines Reviews an eine Cloud-Sitzung: Der Startbefehl lief nicht ohne Terminal, und `dispatch.py` startete ihn ohne.

**Was sich ändert.**
- Eine Remote-Phase mit `"runner": "tmux"` startet den Übergabebefehl jetzt in einem tmux-Fenster.
- `log` und `say` erreichen dieses Fenster.
- `list` zeigt `HAND-OVER FAILED (exit N)`, wenn die Übergabe mit Fehler endete, statt die Phase als laufend auszugeben.

## v2.24.0 — `pushed` wird geprüft, Befunde der Greenfield-Prüfung behoben · 2026-09-24

**Warum.** Im Referenzprojekt meldeten Worker an einem Tag dreimal `pushed`, bevor die Arbeit auf origin lag. Der Steward startete daraufhin die nächste Phase auf einem Branch ohne diese Arbeit.

**Was sich ändert.**
- `report.py pushed` verweigert jetzt, solange der Branch nicht mit dem HEAD des Worktrees auf origin liegt oder origin seit Phasenstart keinen neuen Commit hat.
- `dispatch.py` gibt den Startpunkt als `PROCESS_PHASE_BASE` mit.
- `--force` bleibt für ein unerreichbares origin und markiert die Meldung als unverifiziert.
- Eine Greenfield-Prüfung durch einen unabhängigen Agenten (leeres Repo, alle Harnesses, `regulated`, Hooks, Spec Kit, ein Tier-2-Durchlauf) fand keinen Blocker. Behoben wurde:
  - `template_update.py` verdoppelte bei jedem Lauf die Quotes leerer String-Antworten (`github_repo: ''`). Es erkennt jetzt eine HEAD-Installation vor dem Lauf statt an copiers Downgrade-Fehler.
  - `scripts/process/.gitignore` und `.process-work/.gitignore` halten `__pycache__/` und die Update-Deltas aus dem Worktree.
  - Das Spec-Kit-Setup entfernt die drei Skills auch unter `.github/skills` (Copilot).
  - `start-here.md` nennt `speckit` und `design-contracts` im Standard-Setup.
  - `workflow.md` sagt, dass `/report`, `/steward` und `/finish` Claude-Code-Commands sind und andere Harnesses die Skripte direkt aufrufen.
  - `rehydrate.py --check` bestätigt Erfolg, `train.py plan` ohne Commits hält statt zu scheitern, `finish.py` nennt `publish_and_prune` nur für Änderungen mit Spec.
- Das README ist neu und schlank, mit Verweis auf den Überblick, der jetzt auch englisch vorliegt (`docs/OVERVIEW.md`).

*Dokumentation als Einstieg, ohne Template-Änderung.*
- `docs/UEBERBLICK.md` (und inhaltsgleich als PDF) erklärt den Prozess in elf Kapiteln und ist der neue Einstieg aus dem README.
- BOOTSTRAP nennt die fünf tatsächlichen Fragen, empfiehlt für Updates `template_update.py` statt eines Beispiel-Dictionaries, das Module abgeschaltet hätte, und erklärt parallele Agenten (Modellpolitik, `rehydrate.py --install`, Steward, Dispatch, Zug). Beides wurde an einem frischen Headless-Render nachgeprüft.
- SYSTEM-REQUIREMENTS nennt GitLab und `parity` nicht mehr, dafür tmux und die Koordinationsskripte.
- Das öffentliche Repo nennt das Ursprungsprojekt nur noch als Referenzprojekt und enthält keine Betriebsdetails, Klientenbezüge oder Vornamen mehr. Die Neutralitätslisten der Tests bleiben.

*Lizenztext im gerenderten Repo, SBOM erzeugt statt gepflegt.*
- Warum: Das Template lieferte den Lizenztext nicht mit, obwohl Apache 2.0 ihn bei Weitergabe verlangt. Die Repo-SBOM war von Hand gepflegt und stand auf v1.37.0.
- Jedes eingerichtete Repository erhält `docs/process/LICENSE` (Apache 2.0, identisch mit dem Repo-`LICENSE`; ein Test hält beide gleich) und `docs/process/NOTICE.md`. Die Lizenz gilt für die gerenderten Prozessdateien, nicht für Code und Inhalt des Projekts. Geänderte Prozessdateien tragen einen Änderungshinweis.
- `tools/gen_sbom.py` erzeugt jetzt `docs/SBOM.md` und `docs/sbom.cdx.json` (CycloneDX 1.5, mit Hashes und Abhängigkeitsgraph, deterministisch) aus `pyproject.toml` und `uv.lock`.
- `test_sbom.py` lässt CI rot werden, sobald eine der beiden Dateien veraltet.

## Sub-Projekt-Tabelle (SP1–SP24)

Die Tabelle wurde bis SP24 gepflegt; ab SP25 trägt das Narrativ oben die Historie allein.

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

## v2.23.0 — Lane-Sperre nach Lane und Phase · 2026-09-24

**Was sich ändert.**
- `dispatch.py` wertet die Lane-Sperre jetzt nach Lane und Phase aus statt pauschal.
- `lane.py status` wird zeilenweise gelesen. Ein gehaltenes `full` sperrt nur `execute` (Plan und Review laufen unter dem Zug). Ein gehaltenes `scoped` oder eine unbekannte Lane sperrt alles.
- Eine Remote-Phase sieht weder `max_workers` noch Lane, denn ihre Last liegt auf dem anderen Host.
- `--dry-run` nennt die Regel, die erlaubt oder verweigert hat, und behält bei Verweigerung Exit 3.
- `tower.md` und der Docstring sagen dasselbe.

## v2.22.0 — Phasen auf einem anderen Host · 2026-09-24

**Warum.** Der Steward im Referenzprojekt stellte fest: Der Engpass ist die CPU des Steuer-Hosts, nicht die Zahl der Plätze. Reviews binden viel davon und brauchen nur git.

**Was sich ändert.**
- Die Policy kennt `phases.<phase>` mit `command`, `runner` und `remote: true`.
- Ein Remote-Phase-Start legt keinen Worktree an. Der Befehl ist die Übergabe (Cloud-Sitzung, ssh). Der Branch muss auf origin liegen. Der Prompt weist den Worker an, mit `--sync` unter eigenem `PROCESS_HOST` zu melden.
- `list` zeigt REMOTE, `stop` vergisst nur den Record, `tower.py --remote` sieht die Meldungen.
- `tower.md` sagt, warum Reviews zuerst wandern (git-only, CPU-schwer, und ein frischer Klon auf einem anderen Host ist Unabhängigkeit) und dass ein Push von dort keinen lokalen Pre-Push-Hook durchläuft.
- `rehydrate.py` druckt nur die letzten zwölf Entscheidungen eines Plans. Ein Plan mit 113 DECISION-Zeilen ist ein Log, und jede Kompaktierung zahlte ihn.

## v2.21.0 — Aus dem ersten Steward-Tag · 2026-09-23

**Warum.** Zwei Befunde des Owners, beide aus dem Betrieb.
1. Der Steward ließ einen Worker eine Stunde auf `planned` warten, weil er nur alle 30 Minuten tickte und gerade eine Frage durchreichte. Die Anleitung kannte keine Wache.
2. Ein Gate war im Zug rot, im Root nicht reproduzierbar. Der Staging-Worktree lag unter `.git/process-train/`, und ein Dateilister, der jeden Pfad mit `.git`-Segment überspringt, sah einen leeren Baum.

**Was sich ändert.**
- Claude Code hat eine Wache: `Monitor` auf `tail -f` der Reports-Datei weckt den Steward beim nächsten `planned`/`pushed`/`blocked`/`review-pass`/`done` sofort. Sie lebt maximal 30 Minuten und wird bei jedem Wecken neu gestellt. Der `/loop`-Takt bleibt Rückfallebene (ein `DECISION NEEDED` ohne `blocked` sieht nur der Tower).
- Phasenwechsel warten auf niemanden: nach `planned` sofort `execute`, nach `pushed` sofort `review`. Der Owner wird informiert, nicht gefragt.
- Der Staging-Worktree liegt jetzt als Geschwister neben dem Root (`<root>-train`, wie die Dispatch-Worktrees). Nur Logs bleiben im git common dir.

## v2.20.1 — Subagenten im Worker: Lesen auslagern, nie die Änderung · 2026-09-23

**Was sich ändert.**
- `/execute` sagt jetzt, wofür ein Worker Subagenten nutzt: Suche über die Codebasis, Diagnose aus langen Testläufen, Doku-Abgleich. Viel lesen, wenig zurückgeben.
- Es sagt auch, wofür nicht: die Änderung selbst. Der Subagent kennt weder Kernel noch Ledger, und der Worker würde einen Commit signieren, den er nicht gesehen hat (Regel 1). Die Ausnahme bleibt das `[P]`-Protokoll.
- `rehydrate.py --install` behält die Escapes der Settings-Datei bei.

## v2.20.0 — Re-Hydrierung als Mechanismus, nicht als Satz · 2026-09-23

**Warum.** Bisher stand nur im Kernel „nach einer Kompaktierung lies Kernel, Regeln und Ledger neu". Das ist ein Satz, der die Kompaktierung überleben muss, vor der er warnt. Dem Owner fiel auf, dass Worker das nicht tun.

**Was sich ändert.**
- Neu `scripts/process/rehydrate.py` druckt, was `/prime` liest, und nichts mehr: Kernel-Block, Pflichtregeln, aktive Pläne mit Tier/Issue, DECISION-Ledger, offene DECISION-NEEDED-Fragen mit dem Hinweis „nicht selbst entscheiden", nächste Aufgabe, State-File, Journal-Shard. Es läuft als Claude-Code-`SessionStart`-Hook für `compact|resume`.
- `rehydrate.py --install` trägt den Hook idempotent in `.claude/settings.json` ein, ohne den Rest der Datei anzufassen (sie bleibt Projekteigentum). `--check` sagt, ob der Hook da ist.
- `/prime` bleibt für die Fälle, die der Hook nicht abdeckt. `start-here.md` beschreibt den Mechanismus.
- `dispatch.py` ersetzt im `command` der Policy auch `{branch}` und `{issue}`, damit eine Harness die Sitzung benennen kann. In Claude Code macht `--remote-control={branch}` jeden Worker in der Claude-App sichtbar (die `=`-Form, sonst frisst der optionale Name des Flags den Prompt).

## v2.19.2 — Fragen als Menü · 2026-09-23

**Was sich ändert.**
- Der Steward reicht eine Worker-Frage nicht mehr als Absatz durch, sondern als Auswahl.
- Wo die Harness ein Frage-Werkzeug hat (Claude Code: `AskUserQuestion`): eine Frage je Worker, mit den Optionen des Workers als anklickbare Antworten. Die Empfehlung steht zuerst und ist als „(Recommended)" markiert. Issue, Branch und Lage stehen im Fragetext.
- Ohne Werkzeug: eine nummerierte Liste.
- Bis zu vier offene Fragen in einem Aufruf, älteste zuerst.

**Wirkung.** Funktioniert in der App und per Remote Control.

## v2.19.1 — Zweites unabhängiges Review (v2.18/v2.19): 19 Befunde eingearbeitet · 2026-09-22

**Warum.** Ein frischer Reviewer las Dispatch, Tower, Train, Steward und Modellpolitik ohne Vorwissen. Die harten Befunde:
- tmux-Worker galten ewig als lebendig (die Shell-PID war nicht der Worker).
- `stop` konnte fremde Prozesse treffen (recycelte PID, PID 0 = eigene Gruppe).
- Ein fremdes Verzeichnis am Worktree-Pfad wurde als Worktree akzeptiert.
- Fragen im Worktree eines Workers sah der Tower nicht (er las nur den eigenen).
- Die Modell-KPIs zählten Runden je Meldung statt je Issue.
- Der Prompt lief trotz Doku durch eine interaktive Shell.
- Der Steward hatte Anweisungen ohne Mechanismus („Dateiwache", „Nachricht ins Fenster").

**Was sich ändert.**
- `dispatch.py` neu:
  - Lebendigkeit ist der Pane-Zustand (`pane_dead`, `remain-on-exit`), nie eine Shell-PID.
  - Records tragen PID plus Startzeit; `stop` beendet nur den aufgezeichneten Prozess.
  - Das Fenster läuft eine nicht-interaktive `sh` mit exakter POSIX-Quotierung und `exec`.
  - `{model}`/`{prompt}` werden auch innerhalb eines Tokens ersetzt.
  - `CLAUDECODE`/`CLAUDE_CODE_*` werden für beide Runner entfernt.
  - `issues.json` findet den Branch eines Issues auch nach einem Stop.
  - Der Prompt beginnt mit dem Slash-Befehl und trägt das Frageprotokoll.
  - Neu: `dispatch.py say <branch> "<Text>"` tippt eine Zeile in einen tmux-Worker.
  - `log` zeigt bei tmux den Bildschirm (ein TUI-Log ist Escape-Codes), sonst den Log-Schwanz ohne ANSI.
  - Die Dirty-Prüfung zählt Untracked mit.
- Tower:
  - `questions` liest jeden Worktree dieses Klons und per `git show` die Branches anderer Hosts (`--remote`).
  - Die Fragezeile verträgt Fettdruck und fehlendes „wer".
  - `sessions` zeigt den Zustand (live/dead/gone/unknown).
- Train: Ein offener `DECISION NEEDED` hält den Branch vom Zug.
- `process_context.py` führt `open_questions` je Plan (`/prime` sieht, worauf gewartet wird).
- KPI `models`: Ein Issue ist eine Einheit, das zuletzt gemeldete Modell je Phase besitzt sie, Runden zählen einmal je Issue.
- Steward-Anleitung ohne Erfindungen: Takt per `/loop`, keine Dateiwache im Prozess; Antworten per `say` an den fragenden Worker, nie zwei Schreiber auf einem Plan.
- Trust-Grenze der Policy (`command` läuft auf dem Steward-Host, wie CI-Konfiguration zu prüfen) in `tower.md` und der Policy selbst.
- Hinweis auf Berechtigungen (`-p` braucht eine Freigabe, interaktiv ggf. Trust-Dialog).

## v2.19.0 — Sichtbare Worker und ein Frageprotokoll · 2026-09-22

**Warum.** Maintainer-Erfahrung mit dem ersten Steward: „ich sehe zu wenig, Fragen kommen spät und ohne Kontext". Zwei Entwurfslücken, jetzt geschlossen.

**Was sich ändert.**
- **Worker als tmux-Fenster.**
  - Policy `runner: tmux`, `tmux_session`. `dispatch.py` öffnet je Worker ein Fenster einer tmux-Session, interaktiv und vom Menschen zu öffnen.
  - Die Ausgabe geht per pipe-pane ins Log. Der Start läuft als Shell, Pipe, send-keys, damit die erste Sekunde nicht verloren geht und die TUI ihr tty behält.
  - `dispatch.py log <branch>`.
  - Der Tower führt `sessions` mit letzter Ausgabezeile und Alter je Worker.
- **Frageprotokoll.**
  - Eine Frage an den Owner ist eine Zeile im Plan: `DECISION NEEDED <Datum> <Worker>: <Frage> — options: …; recommendation: …` plus `blocked`.
  - Der Tower führt `questions` und meldet sie als hohen Befund.
  - Die Antwort wird als `DECISION`-Zeile zurückgeschrieben, der Worker liest den Plan. Notizen bis 1000 Zeichen.
- **Der Steward wacht statt zu ticken.** Dateiwache auf Meldungen und Pläne, der Takt nur als Rückfallebene. Fragen werden vollständig und sofort durchgereicht: Issue, Branch, Frage, Optionen, Empfehlung, Lage.

Details: SP75

## v2.18.0 — Dispatch und Modell-Policy · 2026-09-21

**Warum.** Zwei Maintainer-Fragen: „startet das System die Sessions selbst?" (nein, bis jetzt) und „je Phase ein anderes LLM?" (ja, weil die Phasen über Artefakte getrennt sind: Plan und Decisions-Ledger, dann das Bundle).

**Was sich ändert.**
- `docs/process/model-policy.json` ist die eine Stelle, an der man dreht. Sie enthält Tier × Phase → Modell, den projekteigenen Startbefehl als Vorlage (`{model}`, `{prompt}`; der Prompt ist EIN Argument, nie durch eine Shell) und `max_workers`. Sie ist projekteigen und gehört in `.process-owned`.
- `dispatch.py` startet je Phase eine abgesetzte Session im Worktree des Branches (`start --issue N --phase plan|execute|review`, findet den Branch des Issues wieder). Es führt Buch in `.git/process-dispatch/`, zeigt Liveness (`list`) und stoppt nur eigene Kinder und nur bei committetem Baum (`stop`, `--force`). Es weigert sich, wenn `max_workers` erreicht oder die Lane gehalten ist.
- Messen statt Bauchgefühl: `report.py --model` (oder `PROCESS_MODEL`/`PROCESS_PHASE` aus dispatch) hält fest, welches Modell welche Phase fuhr. `process_kpis.py models` (Telemetrie) schneidet Review-Runden bis zum Pass und Blocks nach Tier × Phase × Modell. Das ist ehrlich ein Proxy mit Konfidenz, die Zahl, an der die Policy gemessen wird.
- `/steward` teilt über dispatch zu und ändert Modelle nur über die Policy-Datei.

Details: SP74

## v2.17.3 — Unabhängiges Review von Tower, Zug, Report, Designvertrag und Ledger · 2026-09-21

**Warum.** Maintainer: „check nochmal alles durch, ohne Bias". Ein frischer Reviewer ohne Kontext fand 26 Befunde, sechs davon hoch, alle mit Repro.

**Was sich ändert.**
- Zug:
  - Das Tier aus dem Roh-Text las eingezäunte Beispiele als Deklaration (jetzt `_unfenced` wie im Review-Gate).
  - Ein de-datierter Slug ließ einen Januar-Pass einen September-Plan gleichen Namens klären (jetzt die Eindeutigkeitsregel des Gates).
  - Ein Push nach origin ohne Vorfahren-Prüfung konnte ein main ohne lokale Commits veröffentlichen (jetzt Abbruch).
  - Ein gescheitertes lokales `branch -d` löschte trotzdem auf origin (jetzt gekoppelt und gemeldet).
  - Die Bisektion beschuldigte bei rotem main den ersten Kandidaten (jetzt Basis-Check: rotes main beschuldigt niemanden).
  - Konflikt-Aussteiger blieben stumm (jetzt `blocked`-Meldung).
- Tower:
  - main und `.process-work/` erzeugten Überlappungs-Befunde.
  - Ein README zählte als Plan.
  - Ein lokal anders benannter Branch überlappte mit sich selbst auf origin.
  - Ein fehlgeschlagener Fetch war unsichtbar (jetzt Befund `remote-unreachable`, kein `--prune`).
- Report:
  - Hostnamen wurden am ersten Punkt gekappt (`build.eu`/`build.us` teilten einen Ref).
  - Timeouts blieben ungefangen.
- Designvertrag:
  - `Decision: GO/NO-GO meeting` galt als GO.
  - Eingezäunte Beispiele zählten.
  - Jede 64-Hex-Zahl im Review galt als Siegel (jetzt nur eine benannte `manifest.sha256:`-Zeile).
  - Eine Unterüberschrift mit ID zählte als zweite Definition.
- Siegel: Ein verschachteltes `manifest.json` war vom Siegel ausgenommen.
- Ledger: `--full` prüfte neu, schrieb aber nicht zurück, ein vergifteter Eintrag überlebte (jetzt baut `--full` den Ledger neu).
- Doku an den Code angeglichen, Bedrohungsmodell des Towers ehrlich benannt.

## v2.17.2 — Anleitung verdrahtet; der Steward hält das Repo sauber und die Issues geschlossen · 2026-09-20

**Warum.** Maintainer-Frage „ist die Anleitung angepasst?": Nein, war sie nicht. Tower, Report, Zug und Steward standen nur in ihren eigenen Docs.

**Was sich ändert.**
- workflow.md „Parallel agents" erklärt die vier und sagt ausdrücklich, dass ohne Steward jede Session autonom bleibt: Gates und /finish tragen weiter, der Tower macht nur sichtbar, der Zug nur billiger.
- /plan, /execute, /review und /finish nennen ihren `/report`-Zustandswechsel. Der Zug nennt den Weg am /finish-Merge vorbei.
- README-Commands-Liste.
- Steward, Housekeeping-Abschnitt: täglich `tidy.py --apply` für den sicheren Teil, Owner-Frage für das, was tidy nur listet, `remote-residue` aus dem Tower.
- Steward, Issues-Abschnitt: Worker besitzen ihre Claims und Closes. Der Steward schließt Nachzügler mit dem Merge-Ref, macht Befunde zu getypten Issues und gibt tote Claims nach zwei Stunden frei.
- Der Zug druckt je gemergtem Branch die referenzierten Issues.

## v2.17.1 — Rückstand ist kein Flug · 2026-09-20

**Warum.** Erster Remote-Lauf im Referenzprojekt: Juli-Branches, tausende Commits hinter main, erschienen als „anderswo in Flug".

**Was sich ändert.** Ein Branch ohne Commit seit 14 Tagen wird gezählt statt gelistet und als ein Befund `remote-residue` gemeldet.

## v2.17.0 — Tower über Hosts hinweg · 2026-09-20

**Warum.** Maintainer-Anforderung: Der Prozess bleibt host-agnostisch. Im Referenzprojekt läuft die Steuerung auf einem Host, ein abgesetzter Worker auf einem zweiten. Der einzige Kanal, den jeder Host schon hat, ist git, also ist git der Transport.

**Was sich ändert.**
- `report.py --sync` (oder `PROCESS_REPORT_SYNC=1`) veröffentlicht die Meldungen eines Hosts als Blob unter `refs/process/reports/<host>` auf origin. Kein ssh, nichts auf einem Branch committed.
- `tower.py --remote` (oder `PROCESS_TOWER_REMOTE=1`) holt origin und diese Refs.
- Branches anderer Hosts erscheinen als `elsewhere` mit Vorsprung, Pfaden in Flug und Alter. Sie nehmen an der Überlappungsprüfung teil und können stale sein wie ein lokaler Worker.
- Die Meldungen aller Hosts werden zusammengeführt; je Worker gewinnt die jüngste.
- Starten und Stoppen auf dem anderen Host bleibt dessen Mechanismus; die Steward-Regel ändert sich nicht.

## v2.16.1 — Zugplan ohne Reste · 2026-09-20

**Warum.** Erster Lauf im Referenzprojekt: 350 bereits gemergte Branches erschienen als „nothing ahead".

**Was sich ändert.** Rückstände sind Sache von `tidy.py`, keine Kandidaten. Der Plan zeigt nur Branches mit Vorsprung.

## v2.16.0 — Merge-Zug und Steward-Rolle · 2026-09-20

**Warum.** Maintainer-Wunsch: Aufträge sammeln und zu einem günstigen Zeitpunkt effizient mergen und deployen, statt dass dreizehn Agenten dreizehn Volläufe und Deploys zahlen.

**Was sich ändert.**
- Neuer Merge-Zug `train.py`. `plan` zeigt, wer einsteigen darf und warum nicht; das Ergebnis wird berechnet, nie behauptet.
- Einstieg nur mit archiviertem Plan auf dem Branch und klärendem REVIEW-Pass oder Waiver. Eine Worker-Meldung gilt nur als Zeiger, nie als Ersatz für einen fehlenden Pass.
- Einstieg außerdem nur ohne Datei-Überlappung mit einem bereits eingestiegenen Branch und ohne rotes Gate.
- Abfahrt bei `--min-candidates` oder `--max-wait-hours`, nur bei freien Lanes; `--force` fährt sofort.
- `run` legt einen Staging-Branch aus main im eigenen Worktree an und merged die Kandidaten in Wartereihenfolge (Konflikt = aussteigen). Prozess-Gates und die volle Suite laufen EINMAL auf dem kombinierten Baum.
- Bei Rot findet eine Präfix-Bisektion den ersten Verursacher; er steigt aus und wird als `blocked` gemeldet.
- Bei Grün folgen Fast-forward von main, `--push`, das Löschen der Branches, `done` je Worker und `--deploy` einmal.
- Neue Steward-Rolle (`/steward`): Tower lesen statt Sessions befragen, Befunde nach Schwere abarbeiten, zuteilen, umlenken. Nur eigene Kinder stoppen, und nur nach committed Plan und Decisions. Den Zug abfertigen und dem Owner nur bei Ereignis schreiben.
- Der Steward implementiert, reviewt und zertifiziert nie. Die Modellwahl richtet sich nach dem Tier, das Budget gilt je Issue.
- Doku: `docs/process/train.md`.

Details: SP73

## v2.15.0 — Tower: berechnete Lage für parallele Arbeit · 2026-09-20

**Warum.** Die Idee des Maintainers: ein Agent, der viele Worker koordiniert, mit ihm spricht, Probleme findet und Ressourcen steuert. Bevor ein Agent urteilt, braucht er eine Lage, die nicht erzählt, sondern berechnet ist. Dieser deterministische Kern des Steuermanns liefert sie.

**Was sich ändert.**
- Neu `tower.py`: eine Tabelle aus Zustand, den der Prozess schon führt. Sie enthält alle Worktrees des Klons mit Vorsprung/Rückstand, Pfaden in Flug, Dirty-Zahl und Minuten seit dem letzten Commit.
- Außerdem Überlappungen zweier Worktrees auf derselben Datei (hoch) oder demselben Verzeichnis (niedrig), aktive Pläne mit Tier, Issue, Decisions-Zahl und design-contract-Bindung, Reviews des Tages, rote Gates mit Alter, Lanes, wo es sie gibt, und Worker-Meldungen.
- Deterministische Befunde mit Begründung: Überlappung, Tier-2+-Plan ohne Issue, Plan ohne Decisions-Ledger, Plan ohne Tier, chronisch rotes Gate, stiller Worker ohne Commit und Meldung seit einer Stunde, blockierter Worker, Branch weit hinter main. Optionen: `--json`, `--min-severity`, `--stale-minutes`.
- Worker-Protokoll (`/report`, `report.py`): planned/pushed/review-pass/blocked/done/idle, eine Zeile je Zustandswechsel in das gemeinsame Git-Common-Dir des Klons, nie committed.
- Doku: `docs/process/tower.md`.

**Wirkung.** Der Tower entscheidet nichts und redet mit niemandem. Er ist die Eingabe des Steuermanns, damit dessen Tokens in Urteil fließen (zuteilen, umlenken, beenden) und nicht in Nachfragen bei dreizehn Workern.

Details: SP72

## v2.14.4 — Kein Push wartet blind · 2026-09-18

**Warum.** Befund 2026-09-18 im Referenzprojekt: Der pre-push-Hook stand hinter einem Volllauf an, und der Tool-Call des Agenten starb nach 40 Minuten bei 96 % der Scoped-Tests, fünfmal hintereinander.

**Was sich ändert.**
- Neue Regel in git-hooks.md und `/finish`: Ein Hook, der Minuten laufen kann, wartet begrenzt und bricht mit Halter und Ausweg ab.
- Die Evidenz entsteht entkoppelt im Hintergrund (Certify-Schritt, Baum-Zertifikat); der Push liest sie.
- Das Werkzeug bleibt projektspezifisch. Im Referenzprojekt sind es ein Lane-Skript mit zwei Lanes und ein Certify-Ziel.

## v2.14.3 — Integritäts-Ledger im Review-Gate · 2026-09-15

**Warum.** Befund im Referenzprojekt: 628 digest-gebundene REVIEW-Zeilen, je Zeile mehrere git-diffs, eine kanonische Diff großer Spannen ~3 s. Der pre-push-Gate wurde nie fertig. Die Eingaben einer Verifikation sind im Klon unveränderlich, also auch ihr Ergebnis.

**Was sich ändert.**
- Ein einmal geprüfter Record wird in `.git/process-review-integrity` gemerkt, „ok" wie Mismatch. Ein erfundener Digest bleibt bei jedem Lauf rot, ohne neu gerechnet zu werden.
- Shards, die der Push selbst ändert, werden immer frisch geprüft. Fehlende Commits werden jedes Mal neu gesucht.
- `--full` oder `PROCESS_REVIEW_INTEGRITY=all` prüft alles; `PROCESS_REVIEW_INTEGRITY=in-flight` prüft nur die geänderten Shards (CI-Schalter für riesige Journale).

## v2.14.2 — Plan-Bindung an den genannten Vertrag · 2026-09-15

**Warum.** Erster Lauf im Referenzprojekt: ID-Familien sind surface-übergreifend (E1 ist auf Web wie in der App eine Ebene). Ein App-Plan wurde gegen den Web-Vertrag geprüft, und `C8` galt nicht als `C08`.

**Was sich ändert.**
- Ein Plan wird nur gegen den Vertrag geprüft, den er nennt (Pfad oder `design-contract: <surface>`-Zeile).
- Ein Plan mit Familien-IDs ohne Nennung bekommt genau eine Note.
- Nullen sind keine Identität.

## v2.14.1 — Siegel-Interop mit Render-Kit-Freezern · 2026-09-15

**Warum.** Anlass: drei bereits gesiegelte Runden im Referenzprojekt.

**Was sich ändert.**
- `seal.py --verify` und das design-contracts-Gate lesen auch das Manifest eines projekteigenen Render-Kit-Freezers.
- Dabei gilt: `files` als Liste `{path, sha256}`, Abhängigkeiten als `externalDependencies` mit ordnerrelativen `../..`-Pfaden, `manifest.sha256` in sha256sum-Form `<hex>  manifest.json`.
- Es bleibt dieselbe Formel und ein Verifizierer.

## v2.14.0 — Design-Verträge als Modul · 2026-09-15

**Warum.** Generalisiert aus der Praxis im Referenzprojekt für Web und App: UI-Arbeit scheiterte wiederholt daran, dass jeder Agent etwas Plausibles rendert und niemand sagen kann, welches Bild *richtig* war. Im Referenzprojekt geheilt durch je Surface einen Designvertrag mit stabilen IDs, gesiegelte Render-Runden als Referenz, unabhängiges Review mit GO und Amend-before-Code.

**Was sich ändert.** Das Template macht daraus ein Modul im Standard-Set, inert bis zum ersten Registry-Eintrag:
- **Registry** (`docs/process/design-contracts/<surface>.json`): Vertrag, Status draft/accepted, sha256-Pin, ID-Familien, ADR, Review, gesiegelte Referenz, Code-Pfade.
- **Gate** `check_design_contracts.py`. Hart bei: Pin-Drift ohne Re-Pin, doppelt definierter ID, accepted ohne ADR oder ohne Review mit `Decision: GO`, Review mit anderem Siegel als die Referenz, Referenz mit gebrochenem Siegel, aktivem Plan, der eine ID zitiert, die der Vertrag nicht kennt. Note bei: opakem Pin, Draft, Boards aus älterem Vertrag, Surface-Push ohne zitierte ID.
- **`seal.py`**: Manifest und sha256 über Rundenordner und deklarierte Abhängigkeiten. `--verify` schlägt auf editierte, fehlende und undeklarierte Dateien fehl; Drift einer Abhängigkeit ist Exit 2.
- **Vorlagen**: Vertragsgerüst mit §-Blöcken und Amendment-Log, Review-Vorlage mit Rubrik/GO/Siegel-Hash, Runden-README mit Ablauf.
- **Bindung ohne neue Kettenglieder**: R5 nennt jetzt auch die Vertrags-IDs. D8 beurteilt das AFTER-Bild gegen das gesiegelte Board der zitierten IDs. Review-Checkliste „Surfaces" und Regel 3 entsprechend. Das Review-Bundle nennt den regierenden Vertrag und die zitierten IDs.

**Wirkung.** Die Gestaltung selbst bleibt Menschen- und Reviewer-Urteil gegen die Boards. Render-Kit, Export-QA und Token-Lints bleiben projektspezifisch; das Modul beschreibt nur das Muster.

Details: SP71

## v2.13.0 — Evidenz wird berechnet, Dauerrot bekommt ein Alter · 2026-09-10

**Warum.** Maintainer-Befund aus einem zweiten Einsatz: 15 von 16 Review-Digests wurden nie berechnet. Es war plausibles Hex, das kein Byte-Strom irgendeines Commits erzeugt. Das Gate meldete es bei jedem Lauf, bis es als Dauerrot niemand mehr las. Dritter Maintainer-Befund: Zwei Pläne ohne `tier:`-Zeile waren für jedes Gate unsichtbar, bis sie eine bekamen und sofort zwei Pflichten scharf wurden.

**Was sich ändert.**
- **Evidenz wird berechnet, nie getippt.** `attest.py` schreibt die REVIEW-Zeile: Der Digest wird aus base/head mit der Formel des Gates neu gerechnet, ein veraltetes Bundle wird verweigert, die Grammatik geprüft, die Zeile an den Tagesshard angehängt.
- Die Formel ist EIN Owner in check_review. `CANONICAL_DIFF` pinnt jede git-Config-Stellschraube (algorithm, renames, prefix, abbrev, ext-diff, textconv), damit ein Digest auf jedem Klon gleich verifiziert. Legacy-Digests bleiben gültig.
- Ein Wert, den keine Formel erzeugt, heißt im Gate jetzt FABRICATED und zählt als fehlendes Review.
- **Dauerrot bekommt ein Alter.** gate_runner merkt sich je Gate den ersten roten Tag in `.git/` und druckt das Alter mit jedem Fehlschlag. Digest Sektion 8 zeigt es dem Owner.
- **Abschalten durch Weglassen geschlossen.** Ein aktiver Plan und ein specs/*/plan.md ohne Tier sind jetzt hart; archivierte bleiben Note.

Details: SP70

## v2.12.0 — Entscheidungen im Plan sichern · 2026-09-10

**Warum.** Maintainer-Befund aus einem zweiten Prozess-Einsatz: Entscheidungen im Dialog landen nicht im Plan und gehen beim Kompaktieren verloren. Der Kernel schützt sich selbst, Entscheidungen nicht.

**Was sich ändert.**
- **`## Decisions`-Ledger im Plan**: eine Zeile `DECISION <Datum> <wer>: <was> — because <warum>` je Entscheidung, geschrieben vor dem nächsten Schritt. Plan-, Execute- und Prime-Command sowie workflow.md tragen die Pflicht.
- **Re-Hydration liest sie**: process_context.py gibt das Ledger je aktivem Plan aus, sodass /prime, /execute und /review es nach jeder Kompaktierung wieder sehen. Die Kernel-Direktive nennt den Abschnitt, byte-identisch in allen vier Kopien.
- **Sichtbare Lücke**: Review-Gate-Note für Tier-2+-Pläne ohne den Abschnitt, auch specs/*/plan.md.

**Wirkung.** Das Gate kennt keine fehlende Entscheidung, aber ein Reviewer fragt bei leerem Ledger nach.

Details: SP69

## v2.11.0 — tidy.py räumt Altlasten auf · 2026-09-08

**Warum.** Auf die Maintainer-Frage „räumt der Prozess ausreichend auf?". Gemessen am Referenzprojekt: 353 von 457 Remote-Branches bereits gemergt, 9 von 35 Spec-Verzeichnissen fertig, 5 aktive Pläne älter als zwei Wochen, alles ohne Rhythmus. Nur die Plan-Archiv-Retention funktionierte, weil sie hart im Hook sitzt und der Fix ein Kommando ist.

**Was sich ändert.**
- **`tidy.py`**: ein Report je Altlast mit dem Kommando. `--apply` erledigt den sicheren Teil: gemergte Remote-Branches, fertige Spec-Verzeichnisse via publish_and_prune, Journal falten, alte Archive, template-delta.
- Alte aktive Pläne und stille Issues werden nur gelistet (Owner-Entscheidung).
- **Digest Sektion 7**: dieselben Zahlen jede Woche vor dem Owner.

Details: SP68

## v2.10.1 — Evidenz-Verzeichnis für Spec-Kit-Pläne · 2026-09-08

**Was sich ändert.** Das Evidenz-Verzeichnis eines Spec-Kit-Plans (`specs/NNN-x/plan.md`) wird über das Verzeichnis gefunden, nicht über den Dateinamen `plan`.

## v2.10.0 — UI-Evidenz: Vorher-Nachher-Paare · 2026-09-08

**Warum.** Auf die Maintainer-Frage „sind Screenshots zum Abgleich und zur Erfolgskontrolle hinterlegt?". Sie waren Beweis an der Untergrenze, aber kein Abgleich mit der Absicht und für den Owner unsichtbar.

**Was sich ändert.**
- **DoD D8**: ein Vorher-Nachher-Paar je Viewport, Theme und Zustand unter `.process-work/reviews/<slug>/`, aus dem Review-Report verlinkt. Das Nachher-Bild wird gegen die Absicht beurteilt, nicht nur gegen die Untergrenze.
- **Review-Bundle „UI evidence"**: listet das Paar und jedes Bild, das der Diff berührt. Ein fehlendes Paar ist ein Befund, kein Skip. /review und Checkliste verlangen das Urteil „entspricht der Absicht".
- **Digest Sektion 6**: was sich auf dem Bildschirm geändert hat, mit Evidenzpaaren und geänderten Pixel-Baselines als Pfaden zum Öffnen.
- **`check_baseline_duplicates.py`**: byte-identische Screenshots unter verschiedenen Namen sind Beweis für nichts. Ratchet mit Baseline-Pin.

**Wirkung.** Erster Lauf am Referenzprojekt: 16 Gruppen, darunter „Fehler" identisch mit „teilweise geladen".

Details: SP67

## v2.9.4 — Test-Lanes als geteilte Ressource · 2026-09-07

**Warum.** Befund im Referenzprojekt: Vier Agenten in vier Worktrees ließen ihre gescopten Suiten gleichzeitig laufen, Load 6, alles kroch. Ein kriechendes Gate wird umgangen.

**Was sich ändert.** testing.md: Zertifikats-Transfer am Push und eine flock-Spur je Host. Anstellen statt drosseln, kein Bypass.

## v2.9.3 — Drei Befunde einer Worker-Session generisch geschlossen · 2026-09-07

**Warum.** Drei Befunde einer Worker-Session. Auf einem Worker-Host lief monatelang eine Juni-Kopie von pre-push aus `.git/hooks`, und ein geleaktes GIT_DIR schaltete darüber das echte Repo auf `core.bare=true`. `gh issue comment` läuft über GraphQL, dessen Sekundärlimit stundenlang blockte, während das REST-Budget unberührt war. Anlass für die Deny-Liste: projektinterne Bezeichner in einem Spec-Snapshot.

**Was sich ändert.**
- **Hook-Doktor für `.githooks/`**: Er prüft auch das andere Manager-Modell. Ein getracktes, befülltes Hook-Verzeichnis ohne passendes `core.hooksPath` liest git nie und ist hart, in gate_runner und in finish.
- **REST-Fallback beim Posten**: `publish_and_prune` fällt auf `gh api …/comments` zurück, wenn `gh issue comment` am GraphQL-Sekundärlimit scheitert. Die Verifikation liest zuerst per REST.
- **Deny-Liste vor dem Veröffentlichen**: `.publish-denylist` mit projekteigenen Regexes, die beide Publish-Skripte (publish_and_prune und publish_review.sh) prüfen, bevor etwas das Repo verlässt. Ein Treffer verweigert den Post und nennt die Zeile.

## v2.9.2 — Zertifikate nach dem Bezeugten verschlüsselt · 2026-09-07

**Warum.** Befund im Referenzprojekt: Parallele Worktrees zerhauten sich mit einer Slot-Datei „der zertifizierte Baum" gegenseitig die Zertifizierung.

**Was sich ändert.** Zertifikate sind nach dem verschlüsselt, was sie bezeugen: ein Eintrag je Tree-Hash, nie ein einzelner Slot. Zwischendateien pro Lauf entstehen per mktemp, nie über einen festen geteilten Pfad (testing.md).

## v2.9.1 — template_update.py setzt aufgezeichnete Antworten neu · 2026-09-07

**Warum.** Der erste echte Lauf von `template_update.py` am Referenzprojekt deckte einen Copier-Fallstrick auf: `modules` und `harnesses` sind abgeleitete (`when: false`) Antworten, die copier bei jedem Update aus dem Default neu berechnet. Die aufgezeichnete Antwort gewinnt NICHT, ein abgeschaltetes Modul kommt still zurück (beobachtet: git-hooks samt Anker-Konflikt).

**Was sich ändert.**
- Der Helfer setzt jetzt jede aufgezeichnete Antwort als `--data` neu.
- BOOTSTRAP korrigiert die frühere Behauptung „recorded modules dict wins".

## v2.9.0 — Token-Sparer: Kontextkosten, Journal-Kompaktion, Template-Update · 2026-09-07

**Warum.** Die restlichen drei Kandidaten aus der Maintainer-Frage „was lässt sich noch per Skript automatisieren". Aus der Stunde Hand-Konfliktlösung pro Release, gemessen am Referenzprojekt mit fünf Skripten, einem Doc und einem Command, wird ein mechanischer Port.

**Was sich ändert.**
- **Kontextkosten messen** (`process_context.py --cost`): Was ein Session-Start lädt, gruppiert nach Anker, Commands, Prozessdokus, Produktrahmen, aktive Pläne, State/Journal, alle Journal-Shards, Spec-Verzeichnisse. Dazu die Session-Start-Schätzung und die zehn größten Dateien. Gerechnet wird chars/4, also vergleichbar untereinander, nicht mit der Rechnung. Erst messen, dann kürzen.
- **Journal-Kompaktion** (`compact_journal.py`): Shards älter als N Wochen werden in ein Monatsarchiv gefaltet. Es behält exakt die maschinell gelesenen Records (REVIEW, GRADE) wörtlich und gibt die Prosa an git ab. Gates und trace globben das Archiv wie jeden Shard; gefenzte Zitate fallen mit der Prosa weg. Dry-Run per Default.
- **Template-Update mit Owner-Liste** (`template_update.py` + `.process-owned`): copier update wie gehabt, die Owner-Dateien bleiben wie committet. Das Template-eigene Delta je Owner-Datei (alter Release-Render gegen neuen) landet als Diff unter `.process-work/template-delta/<ref>/`.

Details: SP66

## v2.8.1 — Note-Ledger im gate_runner und finish.py --apply · 2026-09-07

**Warum.** Zwei Token- und Zeitsparer auf die Maintainer-Frage „was lässt sich noch per Skript automatisieren". Jede Gate-Note landet im Kontext des Agenten, und die Notes sind konstruktionsbedingt stabil (Pre-Adoption-Zustände, Platzhalter, Freshness-Hinweise). Also kostete jeder Push dieselben Zeilen und begrub die eine, die sich geändert hat. Der Tail-Checker druckte den deterministischen Teil zum Abtippen.

**Was sich ändert.**
- **Note-Ledger im gate_runner**: Der Runner merkt sich die Notes des letzten Laufs in `.git/`, druckt nur Neues und zählt das Unterdrückte. `--all-notes` zeigt alles. Ein frischer Checkout hat kein Ledger und druckt alles; CI erbt kein lokales Schweigen.
- **`finish.py --apply`**: Der Tail-Checker führt den deterministischen Teil selbst aus. Archiv-Commit und Rebase laufen immer; Merge, Push und Branch-Löschen nur hinter der vollen Suite des Pakets. `--tests CMD` läuft sie, `--tests-passed` behauptet sie.
- Jeder Schritt druckt sein Kommando, der erste Fehler stoppt in einem Zustand, den git erklärt.

## v2.8.0 — Vier Prozess-Erfindungen aus dem Referenzprojekt im Kern · 2026-09-07

**Warum.** Reference-upstreaming: Vier Prozess-Erfindungen aus dem Referenzprojekt, die generisch tragen, werden in den Kern gehoben. Ein Runner, der nicht anläuft, ist ein Launch-Problem mit anderem Owner als eine Regression. Die Registrierung war im Referenzprojekt 25 Tage lang unbemerkt stumm. Dort blockte ein fremdes Entscheidungspapier im Baum einen unbeteiligten Branch.

**Was sich ändert.**
- **Launch-Owner** (`gate_invoke.py`, reines stdlib): die eine Stelle, die entscheidet, womit ein PEP-723-deklarierendes Skript gestartet wird. Kinder des Runners, `finish.py` und das Review-Bundle laufen darüber. „Nicht startbar" wird getrennt von „rot" gemeldet.
- **Hook-Doktor** (dasselbe Modul): `.pre-commit-config.yaml` neben gesetztem `core.hooksPath` heißt, jede Registrierung ist stumm. gate_runner und finish blocken hart. Ein nie installierter Hook ist eine Note bzw. ein finish-Blocker: Ein fehlender Check ist ein Blocker, nie ein Skip.
- **Push-verankerte Presence** (check_review): Ein aktiver Tier-3-Plan, den DIESER Push trägt, braucht den clearing pass hart auf dem Push nach main/master, sonst als Note. „Trägt" heißt: Datei im gepushten Bereich oder Issue per Closing-Trailer/`(#N)`-Subject beansprucht. Das Ziel liest das Gate aus `PRE_COMMIT_REMOTE_BRANCH` des pre-commit-Frameworks oder `PROCESS_PUSH_TARGETS` eines eigenen Hooks. Bekannte Grenze: Ein serverseitig gemergter PR pusht main nie lokal; dort bleibt finish.py der Stop.
- **finish auf Branch-Besitz gescoped**: Nur Pläne, die der Branch trägt oder beansprucht, sind seine Review-Schuld und Archivierungspflicht.
- **UI-Wiederverwendungspflicht**: DoR R5 / DoD D7 verlangen eine Reuse-Map vor der Implementierung und einen Konsumenten-Nachweis danach. Review-checklist „Surfaces": nichts geclippt, 24-px-Ziele nach WCAG 2.5.8, zugänglicher Name auf jedem Button/Link, nichts verdeckt, vier Zustände, beide Themes. Stack-Guides schärfen, senken nie.
- **Ratchet-Muster** (testing.md): Die Baseline pinnt Legacy, neue Befunde und verwaiste Ausnahmen scheitern, die Baseline kann nur schrumpfen.
- **„Unmessbar ist nicht rot"**: Mess-Gates verweigern auf belastetem Host mit eigenem Exit-Code (EX_TEMPFAIL), statt zu scheitern.

Details: SP65

## v2.7.8 — Records sind Leitplanken, kein Beton · 2026-08-29

**Warum.** Auf Wunsch des Maintainers festgehalten.

**Was sich ändert.**
- ADRs und Contracts DÜRFEN geändert werden, wenn die Lösung dadurch dauerhaft tragfähiger, technisch besser oder klarer wird. Das allein ist ein hinreichender Grund.
- Die zwei Ehrlichkeitspflichten sind die ganze Latte. Benennen, was besser wird und warum es langfristig hält (nicht bloß „gerade bequemer"). Die Änderung im selben Aufwand machen wie der Code, der sie voraussetzt (Rule 4): Supersession bzw. versionierter Contract-Wechsel mit allen Konsumenten, nie stille Drift.
- `adr/README` und `contract-first.md` tragen den Grundsatz.

## v2.7.7 — Vier-Zustands-Pflicht für UI-Stories · 2026-08-28

**Warum.** Die Härtungswellen-Analyse zeigte: etwa ein Viertel der Fixes im Referenzprojekt waren Kalt-, Leer- oder Offline-Zustände („unknown stock als leer gerendert", Scope-Fallback beim Laden). „Unknown" ist der Zustand, der unbenannt kaputt ausgeliefert wird: not-yet-resolved ist weder leer noch Fehler.

**Was sich ändert.** Das Spec-Template verlangt pro berührter Oberfläche eine Tabelle mit den Zuständen loading / empty / error / **unknown**, je mit einem erwarteten Verhalten. Das sind die DoR-R2-Zwillinge, für UI konkretisiert.

## v2.7.6 — Die Test-Suite als gemanagtes Asset · 2026-08-27

**Warum.** Der Maintainer-Befund „immer noch extrem viel Zeit für Tests". Gemessen: Die Vitest-Suite wuchs in zwei Wochen um 43 %, es gab 69 E2E-Specs × 2 Plattformen, und Stabilitätsbeweise liefen als 5× Voll-Suite.

**Was sich ändert.**
- **E2E-Budget pro Feature = 1, Floor UND Ceiling.** Ein wachsendes Feature ersetzt seinen E2E-Beweis. Plattform-Varianten nur bei abweichendem Verhalten. Konsolidierungs-Pässe sind Wartung. Jeder pensionierte Test braucht einen benannten billigeren Ersatz.
- **Stabilitätsbeweise scoped × N, voll × 1** (`testing.md`).
- **Test-Estate-Trend im Owner-Digest.** Unit- und E2E-Dateizahlen jetzt vs. vor 14 Tagen, git-basiert, read-only.

**Wirkung.** Wachstum wird sichtbar, bevor es sich wieder wie heute anfühlt.

## v2.7.5 — Zertifikats-Transfer auch bergab · 2026-08-21

**Warum.** Ein Live-Befund des Maintainers: Das Push-Gate zieht die volle Suite, gleich danach läuft der Boundary-Lauf nochmal, ohne Änderung dazwischen.

**Was sich ändert.**
- **Stärkere Evidenz ersetzt schwächere.** Ein Voll-Lauf-Trigger am Push darf auf ein Zertifikat memoisieren, das denselben Baum in einer Obermengen-Konfiguration deckt (Coverage-Lauf ⊇ einfacher Lauf).
- Die Reihenfolge am Kohärenzpunkt ist damit Boundary-Lauf → Push → Review → Merge. Ein Voll-Lauf pro Batch; alle späteren Gates lesen das Zertifikat, statt es neu zu verdienen.
- Klarstellung: Der Review-Preflight fährt nur die Prozess-Gates, nie die Suite.

## v2.7.4 — Push- und Zertifikats-Ökonomie · 2026-08-20

**Warum.** Der Maintainer-Befund „Deploy 20 min, Push-Gate ähnlich".

**Was sich ändert.**
- **Push an Kohärenzpunkten, nicht pro Commit.** Die Push-Gates bepreisen die gepushte Spanne; fünf zusammengehörige Commits in einem Push kosten einen Gate-Lauf. Grenzen: vor Bundle-Bau, vor Session-Ende, oft genug für die Parallel-Sichtbarkeit (`commits.md`).
- **Bezahlte Vollständigkeit ist übertragbar.** Der Boundary-Volllauf schreibt die Zertifikate, auf die spätere Gates memoisieren (Coverage-Tree-Cert). Sie werden in der zertifizierenden Konfiguration verdient, nie behauptet. Ein Deploy-Gate auf demselben Baum wird zum Memo-Hit statt zur Doppelzahlung (`testing.md`).

## v2.7.3 — Test-Ökonomie als generisches Muster · 2026-08-18

**Warum.** Die Maintainer-Frage „voller Testlauf bei jeder Änderung?".

**Was sich ändert.**
- **Selektion nah am Edit, Vollständigkeit nah am Merge.** `testing.md` trägt die Staffel.
- Pro Task und Push läuft die gescopte Menge (Modul-Graph/`vitest related` oder auditierbare Modul-Karte). Ehrliche Voll-Lauf-Trigger gelten für alles, was nicht über Imports wirkt (Config, Tokens, globale Styles, Schema, DI, Fixtures).
- Am Merge-Boundary läuft die VOLLE Suite genau einmal für das ganze Batch. Mehrere Änderungen teilen sich einen Voll-Lauf; Selektion ist nie das letzte Netz.
- `finish.py` druckt den Voll-Suite-Schritt vor dem Merge.

## v2.7.2 — Zwei Gate-Defekte aus dem frischen Klon · 2026-08-17

**Warum.** Zwei Defekte aus dem frischen Klon des Referenzprojekts, dem ersten kalten Prüfstand nach Wochen warmer Sessions.

**Was sich ändert.**
- **Digest-Bindung ehrlich degradiert.** Nach Rebase-Merge und Branch-Löschung existieren die Pre-Merge-SHAs in keinem frischen Klon. Nicht auflösbare Artifact-Commits sind jetzt Note („unverifiable here") statt hartem Rot, das rückwirkend jeden Klon für jede korrekt gebundene historische Review röten würde. Ein Digest-MISMATCH bleibt hart.
- **Tier-Deckel in der Presence-Arithmetik.** Die REVIEW-Grammatik deckelt tier bei 3. Ein Plan auf erweiterter Downstream-Skala (`tier: 4/5`) cleart an der gegateten Decke (min(tier,3)) statt an einer unerfüllbaren Latte, Archiv- und Speckit-Pfad gleichermaßen.

## v2.7.1 — Speckit-Presence und Gate-Hygiene · 2026-08-17

**Warum.** Der Befund im Referenzprojekt: „Slices 009–016 liefen am stärksten Gate vorbei". Die Spec-Kit-Pläne leben in `specs/<dir>/plan.md` und werden nie archiviert. Das Review-Presence-Gate scannte nur `.process-work/plans/archive/` und konnte den Standardweg nicht sehen.

**Was sich ändert.**
- **Speckit-Presence** (`speckit_unreviewed` in check_review): Ein voll abgehaktes tasks.md plus ein Tier-2+-Plan ohne Waiver braucht den clearing pass. `finish.py` blockt hart am Merge-Ritus. Das Review-Gate meldet nur als Note: hart am Push würde jeden Push zwischen letztem Tick und Review röten. `commits.md` benennt die Speckit-Variante des Archiv-Schritts: publish_and_prune statt Archiv-Move; finish druckt die fertigen Verzeichnisse einzeln.
- **Owner-Brief-Note** (speckit-Gate): spec.md ohne Owner-brief-Sektion gibt eine Note. 2 von 6 neuen Specs im Referenzprojekt hatten den Brief vergessen.
- **Waiver-Ehrlichkeit:** Ein Plan mit `issue:`-Anker besitzt seine Waiver dort. Nur trackerlose Waiver werden geflaggt. Der Digest ist gleichgezogen.
- **ADR-Rauschen:** Die Intent-Note entfällt für rejected/superseded; historische Records haben keine Endorsement-Achse.

Details: SP64

## v2.7.0 — Owner-Loop: der Mensch als echter Knoten · 2026-08-13

**Warum.** Der Maintainer-Befund „ich reviewe die Slices kaum — und verstehe die Specs oft nicht". Der Mensch wird ein echter Knoten des Loop-Graphen, mit definierten Eingangs-Kanten statt Polling.

**Was sich ändert.**
- **Owner brief.** Pflicht-Vorspann jeder Spec: fünf Klartext-Sätze ohne Jargon und Dateinamen (Was / Warum / sichtbare Änderung / Risiko / „Your call"). Er führt den staged Issue-Kommentar an und macht das Einflussfenster benutzbar.
- **`human_digest.py`.** Die Eingangs-Kanten als EINE Seite: wartende Specs samt Brief und offenen Fragen, Merges der letzten N Tage, stehende Waiver-Schulden, Fix-Cluster. Read-only; fehlende Quellen werden benannt statt still leer gelassen.
- **Sampling-Audit.** Ein gemergtes Paket pro Woche, deterministisch per ISO-Woche gewählt (kein Re-Rollen). Review by exception statt Diff-Konkurrenz zum Modell-Reviewer (`verification-independence.md`).
- **owner-digest-Workflow.** Wöchentlich Mo plus Dispatch; der Digest geht in die Step-Summary.

Details: SP63

## v2.6.2 — [P]-Gruppen wirklich nutzen · 2026-08-13

**Was sich ändert.** „Parallel edit, serial commit":
- [P]-Tasks laufen als gleichzeitige Subagents im selben Worktree. Die Subagents editieren ihr disjunktes Datei-Paket und liefern Test-Evidenz; sie committen nie.
- Der Orchestrator serialisiert den Schwanz jedes Tasks (atomarer Commit, Checkbox, Gate) in Abhängigkeitsreihenfolge.
- `/plan` schärft [P] auf „kein geteilter Berührungspunkt", inklusive Barrel-Exports, Manifeste und generierte Indizes. Ein falscher Marker wäre eine Working-Tree-Kollision.

## v2.6.1 — Slice-Ökonomie nachgeschärft · 2026-08-13

**Warum.** Der #688-Befund „50 Tasks, extrem lang".

**Was sich ändert.**
- **Task-Korn.** Ein Task = ein Verhalten, Test UND Implementierung. Die TDD-Reihenfolge lebt IM Task, nie als Task-Paar. Der Task ist die Einheit von Planung, Checkbox, Gate-Lauf und Bericht: 50 Tasks, die 30 sein könnten, zahlen das Ritual zwanzigmal umsonst.
- **Tier pro Stage.** Bei Stage-Merges trägt jede Stage ihren eigenen Tier. Eine verhaltensneutrale Extraktions-Stage mit mechanischem Beweis ist Tier 2, auch wenn die verhaltensändernde Stage Tier 3 ist (`risk-tiers.md`).
- **Mechanik vor Urteil.** Alle mechanischen Detektoren laufen VOR dem Review-Bundle und ihre Ergebnisse wandern hinein. Der Modell-Reviewer verifiziert die Mechanik-Schicht, statt sie zu entdecken. Ein grep-barer Befund kostet mechanisch Cents, per Review eine Runde.

Details: #688

## v2.6.0 — Längsschnitt: Muster zwischen Paketen · 2026-08-13

**Warum.** Der Befund im Referenzprojekt: „53 fix-Commits in 5 Tagen, ein Scope-Cluster mit 13 Fixes, jeder einzeln durch alle Gates". Der Prozess regierte das einzelne Paket, hatte aber kein Organ für Muster ZWISCHEN Paketen.

**Was sich ändert.**
- **Fix-Cluster-Advisory** (`process_kpis clusters`): Rule 6 sessionübergreifend; der Zähler lebt in git. Debug-Command, `workflow.md` und Review-Checkliste tragen die Stopp-Regel „dritter Fix am selben Verhalten = fehlende Spezifikation".
- **Invarianten-Heimat.** Decision-Record-Typ `invariant` für featureübergreifende Verhaltensregeln. Eine `## Test`-Pflicht gilt als Enforcement-Zwilling ab Accepted; das decisions-Gate prüft sie.
- **Degradations-Schulden.** `review-waived:`/`spec-waived:` ohne Issue-Ref gibt eine Note „a debt with an owner".
- **KPI-Trigger.** Monatlicher process-kpis-Workflow: Ein KPI ohne Trigger existiert nicht.
- **`/finish`** (`finish.py`): der Merge-Schwanz als EIN Verdikt. Clearing pass, grüne Gates, sauberer Tree, dann der Rest-Ritus in Reihenfolge. Read-only; gebaut gegen die beobachteten Tail-Ausfälle #652/#653/#660.

Details: SP62, #652, #653, #660

## v2.5.2 — Runden-Ökonomie der Review-Schleife dokumentiert · 2026-08-12

**Warum.** Der Maintainer-Befund „bei jeder Abweichung läuft die gesamte Kette". Das `--since`-Delta-Bundle existierte seit v2.3.0, aber kein Dokument und kein Command lehrte es.

**Was sich ändert.** `/review`, `workflow.md` (Review) und `verification-independence.md` beschreiben jetzt die drei Preisregeln:
- Findings einer Runde bündeln: ein Fix-Pass, ein Push. Jeder zusätzliche Head-Commit bezahlt die Push-Gates und Tests erneut.
- Runde 2+ als Delta-Bundle über `--since`. Der Volldiff bleibt digest-gebunden; Tier 3 liest immer voll.
- Einmal rebasen, vor der ersten Runde. Jede spätere Rebase entwertet die Digests.

## v2.5.1 — Modell-Routing als Harness-Default · 2026-08-11

**Was sich ändert.**
- `model:`-Frontmatter auf den Phase-Commands: `/brainstorm` und `/plan` auf dem stärksten Modell (Urteilsdichte: ein Spec-/Plan-Fehler kostet sein Vielfaches stromabwärts), `/review` auf `opus`. Die Execution erbt das Sitzungs-Arbeitsmodell.
- Die `/speckit-*`-Commands bleiben unberührt, da ein Spec-Kit-Update sie überschreibt. Das Routing lebt in den Wrapper-Commands.
- Doku im speckit-Modul aktualisiert.
- Kein neues Gate, keine Config-Achse: Routing bleibt Engine-/Harness-Verhalten.

## v2.5.0 — Sichtbarkeits-Paket: Issue bei der Idee, Stage-Publishing, Review-Ökonomie · 2026-08-08

**Warum.** Aus dem Lebenszyklus-Review des Maintainers. Das Einflussfenster des Menschen ist die Spec-/Design-Phase.

**Was sich ändert.**
- **Issue bei der Idee statt beim Plan.** Das Tracking-Issue entsteht beim Brainstorm-Eintritt. Eine aktive `specs/*/spec.md` ohne `issue:`-Zeile ist hart (issue-before-spec im Issues-Gate).
- **Stage-Publishing.** `publish_and_prune --stage` postet die fertige Spec (und Design) als datierten Read-only-Snapshot-Kommentar ans Issue und prunt nichts. Neue Issue-Kommentare sind Clarify-Input vor `/plan`.
- **Review-Ökonomie für Subagent-Engines.** Task-Reviews nur für Owner-/Integrations-Tasks (Mechanik im Sammel-Checkpoint). Runde 2+ als `--since`-Delta. Die finale Whole-Branch-Review des Engines IST die attestierte Merge-Review: ein Deep-Review auf dem stärksten Modell statt zwei (~5 statt ~9 Läufe pro #651-großem Paket).

Details: SP61, #651

## v2.4.0 — Engine-Freiheit und Hygiene · 2026-08-08

**Warum.** Aus dem Live-Betrieb der SpecKit/Superpowers-Kombination im Referenzprojekt.

**Was sich ändert.**
- „The execute engine is free, the artifacts are not": Subagent-per-Task-Engines sind im Execute sanktioniert, solange die Artefakt-Invarianten halten und die Merge-Review die attestierte bleibt.
- Der **Prose-Tier-Detector** im Review-Gate macht den Drittskill-Fehlermodus laut: Ein Plan erwähnt „Tier N", deklariert aber keine `tier:`-Zeile, sodass alle tier-gekeyten Gates unbewaffnet sind (live auf #651 gefunden).
- **„Merge leaves no residue"** in `commits.md`: Branch löschen, `git worktree remove`/`prune`.
- Der dispatchbare **cleanup-branches-Workflow** (patch-identitäts-basiert, Dry-Run-Default, Open-PR-Schutz), im Repo und im Template.

Details: SP60, #651

## v2.3.0 — Downstream-Backflow aus dem DATEV-Fork · 2026-08-07

**Warum.** Die vier generalisierbaren Beiträge aus dem privaten DATEV-Fork, per Patch-Handoff übernommen (der Fork darf keine PRs stellen).

**Was sich ändert.**
- **Copier-Render-Cache in den Tests.** Jedes Answer-Set rendert einmal pro Session, jeder Test bekommt seine Kopie. Die volle Suite sinkt von ~4,5 min auf ~1,5 min.
- **Gate-Preflight vor dem Review-Bundle.** Rote Gates ergeben kein review-fertiges Bundle; `--skip-preflight` ist der bewusste Ausweg.
- **Begrenzte Delta-Re-Reviews.** `--since` mit Voll-Artefakt-Bindung, mitgeführten Vorbefunden und Tier-3-Ablehnung.
- **Advisory Finding-Ratchet.** `gate=judgement|possible|<rule>` an FINDING-Zeilen; `possible` markiert Automatisierungskandidaten als Note, nie blockierend.

Bewusst NICHT übernommen: Model-Routing, CODEOWNERS-Härtung, Pflicht-SBOM, Plattform-Fixierung (Fork-lokal, deckungsgleich mit dem Lean-Pass) und das decision-adoption-Modul (geparkt, bis Nutzungsevidenz vorliegt; die Intent-Achse trägt die leichte Version bereits).

Details: SP59

## v2.2.0 — Pläne haben genau ein Zuhause; Lizenzwechsel auf Apache-2.0 · 2026-08-07

**Warum.** Beobachtung im Referenzprojekt: Topic-getriggerte Dritt-Skills (Superpowers-Brainstorming/-Planning) mit eigenen Datei-Konventionen können die artefakt-präsenz-abhängigen Pflichten lautlos umgehen. Ein Plan, der nie in `.process-work/plans/` landet, löst weder Clarification- noch Review-Präsenz aus.

**Was sich ändert.**
- `journal-state-plans.md` schreibt „Plans have exactly one home" fest: Skills helfen *in* Phasen, das Artefakt hat genau ein Zuhause.
- Das Review-Gate bekommt den **Unhomed-Plan-Detector**. Eine `tier: 2+`-Deklaration außerhalb der sanktionierten Homes (`.process-work/`, `specs/`, `docs/process/`, Harness-Verzeichnisse) ist hart. Archive sind Historie; Tier 0/1 und gefencte Zitate bleiben außen vor.
- **Spec-before-plan** im Speckit-Gate: Ein aktiver Tier-2+-Plan referenziert sein `specs/`-Verzeichnis oder trägt eine begründete `spec-waived:`-Zeile. Die Spec-Kit-Interrogation zu überspringen ist eine dokumentierte Entscheidung, nie ein stilles Verhalten.
- Lizenzwechsel (2026-08-07, nach v2.1.0): von der Prosperity Public License 3.0.0 (nicht-kommerziell) zu **Apache-2.0**. Der Kern ist bewusst offen (Open-Core-Strategie: künftige kommerzielle Zusatzkomponenten bleiben separate Werke).
- Die MIT-Attribution für die zwei von GitHub Spec Kit abgeleiteten Templates ist nachgezogen (`THIRD-PARTY-NOTICES.md`, auch gerendert in Adopter-Repos; Provenienz-Kommentare in den Dateien).

Details: SP58

## v2.1.0 — Reference-Backflow: vier Prozess-Lektionen und zwei ADR-Gate-Fixes · 2026-08-07

**Warum.** Vier Prozess-Lektionen aus dem Live-Betrieb des Referenzprojekts, die dem generischen Kern nach der Adoption nachweislich noch fehlten. Dazu zwei Brownfield-Defekte am Decision-Records-Gate, die die ADR-Korpus-Übernahme im Referenzprojekt aufgedeckt hat.

**Was sich ändert.**
- **Regel 1 geschärft.** Sub-Agent-Summaries sind `[assumption]` bis zur Stichprobe. Das Stop-Wort „source?" heißt Tool-Beweis oder Rückzug.
- **Review-Runden-Cap im Workflow.** Nach zwei erfolglosen Review→Fix-Runden zurück in die Planung. Das ist das Review-Pendant zur Zwei-Versuche-Regel 6.
- **Bookkeeping-Disziplin in `commits.md`.** Journal, Plan und State fahren im Arbeits-Commit, keine `record`-Ketten. SSOT-lose Evidence kommt in den Issue-Kommentar.
- **Anchor-Budget-Check im doc-drift-gate.** Anchor > 200 Zeilen ergibt eine Note, nie einen Fail. Er ist der mechanische Wächter für den „driftet es beim Refactor?"-Diskriminator.
- **Status-Enum erweitert** um `Rejected` (Vorschlag, der nie galt) und `Deprecated` (galt einmal, jetzt abgeraten). Sonst bliebe ein toter Vorschlag ewig `proposed`.
- **Seed-Record umnummeriert** von `adr-0001` auf `adr-0000`, damit ein bestehender Korpus, der bei 0001 beginnt, kollisionsfrei einziehen kann.

Details: SP57

## v2.0.0 — Lean-Standard: Refactoring auf GitHub + Spec Kit + pre-commit + dev-process-Kernel · 2026-08-06

**Was sich ändert.**
- Das große Refactoring (SP56, lean-standard) stellt den Prozess auf den Standard-Stack GitHub + Spec Kit + pre-commit + dev-process-Kernel um, nach unabhängigem Design-Review (Report: `.process-work/reviews/2026-08-06-speckit-hybrid-design-review.md`).
- Abgebaut: GitLab-CI-Adapter, parity, `attention.py`/`who_is_working.py` (die GitHub-UI übernimmt), `story_order` und die Arbeits-Log-Achse der Registry, der eigene Hook-Installer, das artifact-v1-Zertifikatsritual. Die Telemetrie läuft nur noch auf den drei Ziel-KPIs (Konvergenz, Kosten, CFR). Profile und Toggles weichen dem Standard-Setup mit einzigem `regulated`-Schalter. contract-first und contracts-drift sind zu `contracts` verschmolzen.
- Umgebaut: feature-registry ist jetzt das Feature-Inventar (Capability → Akzeptanz → Test, hermetisch). Die Hooks laufen auf dem pre-commit-Framework. github-master ist registry-frei (Snapshot nach Issue-Nummer, DoR-at-rest, Board-Konsistenz). Das Review ist auf eine Attestierung mit opt-in Diff-Digest reduziert (verifiziert statt Ritual).
- Gebaut: das `speckit`-Modul als Standard-Spezifikationsweg — Constitution-Pointer mit Gate-Guard, EARS-/Test-Pflicht-Overrides, Command-Wrapper mit Kernel-Pflichten, clarification-Gate über `specs/`, `publish_and_prune`-Merge-Ritual mit verifiziertem Publish + SC-Accounting und Flow-Forward-Degradation.
- Der Produktrahmen-Wechsel ist im README dokumentiert, das Exit-Szenario (Pin einfrieren) festgehalten.
- Dazu der Token-Lean-Pass (`process_context.py`, Prime-Diät, analyze/converge nur noch Tier 3).
- Dazu der Windows-Pfad-Fix: kein `|` mehr in Template-Pfaden, die OS-Smoke-Matrix ist wieder grün.
- **Breaking**: Modul-Keys und Install-Dialog sind geändert.
- SP55 (spec-deepening) vertieft die Spezifikationsphase mit Anleihen aus GitHub Spec Kit, schema-erhaltend (Analyse: `docs/analysis/2026-08-06-speckit-comparison.md`):
  - `[NEEDS CLARIFICATION: …]`-Marker-Konvention im Brainstorm statt stiller Annahmen.
  - `design-template.md` als Core-Doc-Scaffold (Intent, Constraints, Touchpoints, nummerierte EARS-ACs, Alternativen, offene Fragen, Tier-3-Threat-Frage).
  - Die Review-Checkliste ist um „Specification quality" erweitert (testbare Kriterien, ehrlich aufgelöste Fragen, Was/Wie-Trennung, DoR-R2-Twins).
  - Fünftes **Core-Gate** (`check_clarification.py`): ein unaufgelöster Marker in einem *aktiven Plan* ist hart (der Plan setzt ein genehmigtes Design voraus), im aktiven Design nur eine Note (mid-flight bleibt grün), das Archiv ist Historie. Ein Fenced-Block gilt als Zitat wie beim Review-Gate.

**Update.** Bestehende Adopter migrieren über `copier update` mit explizitem `modules`-Dict (BOOTSTRAP, „Later").

Details: SP55, SP56

## v1.37.0 — Cross-Platform-Härtung: `git` + `uv` als Runtime-Vertrag · 2026-07-10

**Was sich ändert.**
- `git` + `uv` sind der einheitliche Runtime-Vertrag auf Linux, macOS und Windows.
- Der PEP-723-Gate-Runner braucht kein systemweites Python und kein PyYAML.
- Hook-Installation, Hook-Logik und Issue-Body-Erzeugung gibt es als portable Python-Implementierungen bei kompatiblen Shell-Launchern.
- Claude, Copilot und AGENTS.md sind unabhängig kombinierbar.
- Neu: OS-Smoke-Matrix.
- Manifestwerte werden fail-closed validiert.
- Der Release-Tag muss zur Projektversion passen.

Details: SP54

## v1.36.0 — Methodik-Eignungsprüfung: EARS-Musterkatalog und Spike-Pfad · 2026-07-10

**Warum.** Der Prinzipien-Check der Kette Brainstorm→EARS→Plan zeigte zwei Lücken.

**Was sich ändert.**
- Der **EARS-Musterkatalog** steht in der DoR-Doc: alle fünf Formen (ubiquitous/event/state/unwanted/optional), mit Unwanted-behaviour als natürlicher Form der von R2 geforderten Negativ-Fälle.
- Der **Spike-Pfad** in `workflow.md` gilt für ergebnisoffene Arbeit: timeboxed, der Output ist Wissen (Journal/Design/Decision Record), nie Produkt-Code. Ein Folge-Feature läuft durch den normalen Zyklus, der Prototyp wird nicht befördert. Ein Timebox-Stopp ist ein Erfolg.

Details: SP53

## v1.35.1 — Divers-Audit über v1.35.0: vier neue Blickwinkel, Fixes · 2026-07-10

**Was sich ändert.** SP52 ist ein Divers-Audit über v1.35.0 mit vier bewusst neuen Blickwinkeln:
- Pragmatiker/Ökonomie: Verdict „Prozess mit ungewöhnlich wenig Theater", ca. 5,4k Token Lese-Steuer pro Session, Gates 0,2–0,8 s, Over-Engineering-Kandidaten freigesprochen.
- Multi-Harness-Degradation: 9 Render-Kombinationen.
- Lebenszyklus: Upgrades v1.13.0→HEAD konfliktfrei und byte-identisch, 10x-Wachstum unter 0,9 s.
- Technical Writer über die SP48–51-Prosa.

Gefixt:
- Der Copilot-Anker erhält die Route zu workflow/commits.
- BOOTSTRAP-„Later" ohne `--skip` (stale Kernel nach Upgrade reproduziert) und Hooks-Neuinstallations-Hinweis.
- `trace` ohne Bare-Digit-Rauschen (#7 matchte 68/68 Pläne).
- Das Bundle hat einen `--plan`-Filter und einen harten Unknown-Flag-Fehler.
- Soft-Note für nicht archivierte Tier-2+-Pläne.
- doc-drift scannt die Copilot-instructions-Datei.
- `gate_runner` benennt die Hand-Edit-Ursache.
- No-CI-DoR ist erfüllbar (Hooks als Authority).
- Quick-Fragen mit einem Owner in `workflow.md`.
- Retention-Ehrlichkeit.
- R2 besitzt die vier Akzeptanz-Fälle.
- Etwa 15 Writer-Präzisionsfixes.

Report: `.process-work/reviews/2026-07-10-sp52-diverse-audit.md`.

Details: SP52

## v1.35.0 — State-of-the-art-Abgleich: sechs Lücken geschlossen

**Warum.** Die Recherche (DORA, Diátaxis/arc42, Supply-Chain, Diagrams-as-Code, KI-Guardrails) ergab sechs Lücken.

**Was sich ändert.**
- `testing.md` als Core-Doc: Suite-Form als Pyramiden-Heuristik, Property-based, Regression-Pins, Mutation-Testing auf kritischer Logik, ehrliche Coverage-Decke (Trend statt Schwellen-Gate). Über Regel 5 und die Review-Checkliste verdrahtet.
- `releases.md` als Core-Doc: SemVer, kuratiertes Changelog, Tag-Ritual mit Versions-Dreiklang-Invariante. Über `commits.md` verdrahtet.
- Threat-Frage für Tier 3 in Brainstorm und Review-Checkliste („Was könnte ein Angreifer mit dieser Änderung?" — Assets/Inputs/Trust-Boundaries).
- Diagrams-as-Code-Konvention (Mermaid im Markdown, diffbar im PR; das Gate parst weiterhin keine Diagramme) im arch-docs-Moduldoc und im Overview-Scaffold.
- Plattform-Hygiene im Onboarding-DoR (Secret Scanning + Push Protection, Dependabot/Renovate), ehrlich als Netz-Dienste gerahmt, kein hermetisches Gate.
- Branch-Lebensdauer „Tage, nicht Wochen" in `commits.md` (Small-Batch-Befund hinter Trunk-based).

Details: SP51

## v1.34.1 — Tiefenaudit: ein Blocker geschlossen, SP49-Regression gefixt · 2026-07-10

**Was sich ändert.** SP50 ist ein Tiefenaudit über den bereinigten Stand, mit vier unabhängigen Blickwinkeln mit Ausführungsmandat: adversarial, Kohärenz, Fresh-Adopter, Robustheit.
- 1 Blocker geschlossen: Das Fence-Tracking ist längenbewusst (gequotete Waiver in verschachtelten Fences clearten Review-/Issue-Gate).
- SP49-Regression gefixt: Nur echte Issue-Refs zählen als clearende work-ids; die Ref-Grammatik wanderte nach `check_review` (ein Owner).
- OSError-Diagnosen statt Tracebacks.
- security-floor mit Regex-Backtracking-Budget und Zero-in-Scope-Note.
- `gate_runner` mit Gate-Timeout und bytecode-frei.
- Die letzten `adr_exists`-/`_unfenced`-Kopien sind konsolidiert.
- `gh_board`-Argument-Hygiene.
- BOOTSTRAP-Update-Rezept für HEAD-Installs.
- `start-here`-Reihenfolge und `git init -b main`.
- Commit-Traceability-Konvention.

**Wirkung.** Adopter-Verdict: Ein Solo-Dev erreicht einen grünen Gate-Lauf und den ersten reviewten Change ohne Hilfe.

Report: `.process-work/reviews/2026-07-10-sp50-deep-audit.md`.

Details: SP50

## v1.34.0 — KISS-Cleanup: ein Owner je Verhalten

**Was sich ändert.** SP49 räumt auf Basis von drei parallelen Tiefen-Sweeps (Dead Code, Duplikate, Doku-vs-Code) auf.

Ein Owner je Verhalten:
- `check_review` besitzt die Plan-Feld-Grammatik und `_unfenced` (`check_issues`/`trace` importieren). Die Issue-Regex ist vereinheitlicht, Cross-Repo-Refs clearen jetzt auch das Review-Gate.
- `check_decisions` besitzt `adr_exists` (3 divergente Kopien ersetzt).
- Das Review-Bundle importiert die Kernel-Block-Extraktion (Zweitblock → ehrlich unavailable statt still der erste).
- `gh_json` hat einen Owner im github-issues-Modul.
- Nicht-importierbare Zwillinge (sbom/security-floor-Git-Helfer, EARS/Epic-Heuristik) sind per Template-Test gepinnt.

Funktional:
- Die sbom-Beispiel-Policy no-opte auf Root-Manifesten (bare+`**/`-Paare).
- Tote Manifest-Globs ohne Parser entfernt.
- `sbom` fehlte in allen drei Adapter-Modullisten (Test pinnt auf `copier.yml`).
- `gh_board --push`-No-op-Stub entfernt.
- github-master meldet einen leeren Mirror advisory statt still OK.
- Der `trace`-FINDING-Matcher verlangt `key=value`.

Dazu 12 Doku-Kohärenz-Fixes („one tier weaker" gestrichen, DoR/DoD-Abweichungskanäle getrennt, Copilot-Review-Prompt trägt die Grammatik, u. a.).

Details: SP49

## v1.33.0 — Telemetry-Ehrlichkeit: Individualität von Projekten als bindende Decke

**Was sich ändert.** SP48 dokumentiert die Individualität von Projekten als bindende Decke:
- Zahlen gelten nur projektintern gegen die eigene Baseline (Trends, Verhältnisse, Catch/Escape-Ereignisse als robusteste Klasse).
- Kein projektübergreifendes Benchmarking.
- Cockpit-Schwellen sind Startwerte zur Rekalibrierung.
- Goodhart-/Self-Grading-Vorbehalt.
- Moduldoc-Sektion „honest ceiling", Cockpit-Docstring und README tragen das.
- Moduldoc und Cockpit sind per Template-Test gepinnt.

Details: SP48

## v1.32.1 — Arc-Review über den Tiefe-Bogen: vier Defekte im Bundle-Tool geschlossen · 2026-07-10

**Was sich ändert.** Ein Arc-Review über den Tiefe-Bogen mit zwei unabhängigen Reviewern.
- Vier ausführbare Defekte im Bundle-Tool geschlossen: Fence-Korruption bei Markdown-Diffs, Non-UTF-8-Crash, IndexError bei fehlendem Options-Wert, Subdir-Aufruf verlor Root-Quellen.
- Der Grammatik-Claim ist ehrlich auf die REVIEW-Hälfte begrenzt; die FINDING-Tokens sind per Template-Test an `check_issues` gepinnt.
- Die adr-Auflösung sieht rohe Regeln, Deviation zählt nur als echte Überschrift, der dor-Slot hat ein exaktes Key-Set.
- Doku-Kohärenz: bedingter arch-onboarding-Verweis, Hard-Path-Klausel in github-issues.

## v1.32.0 — Tiefe II und III: Architektur-Grenzen als Floor-Regeln, Review-Bundle

**Was sich ändert.**
- SP46 (Tiefe II — Architektur-Grenzen als Floor-Regeln): Es gibt kein 14. Modul, sondern den bestehenden Owner. security-floor kann per `applies_to` gescopte Regeln schon. Neu: optionales `adr`-Feld je Regel (hängende Links hart), Arch-Beispielregel, Moduldoc-Sektion mit ehrlicher Decke (Regex-Floor, kein Architektur-Review), Ratchet-Trigger und arch-onboarding-Querverweis.
- SP47 (Tiefe III — Review-Bundle als portables Reviewer-Interface): `make_review_bundle.py` (Core) baut das eine self-contained Dokument aus Kernel, Checkliste, Produktrahmen, Plänen, Diff und REVIEW-Grammatik, die direkt aus `check_review` importiert wird. Die FINDING-Tokens sind per Template-Test an `check_issues` gepinnt. Dispatch-Rezepte je Harness stehen in verification-independence, `/review` zeigt auf das Tool.

Details: SP46, SP47

## v1.31.0 — Tiefe I: DoR als Gate

**Was sich ändert.** SP45 macht die Definition of Ready zum Gate.
- `gh_sync` leitet die Ready-Fakten aus dem Live-Issue ab (typed/EARS/`## Deviations`-Body-Note als benannter Escape) und legt sie als `dor`-Slot in den Snapshot.
- Das hermetische github-master-Gate failt hart, wenn eine in-progress-Story ein nicht-Ready-Issue ohne Deviation verlinkt. Proposed ist noch nicht gestartet, done ist Sache des Review-Gates.
- Ein alter Snapshot degradiert ehrlich zur Re-sync-Note.

Details: SP45

## v1.30.1 — Merge-Gate-Review über den v1.26–v1.30-Bogen · 2026-07-10

**Was sich ändert.** Merge-Gate-Review über den v1.26–v1.30-Bogen, zwei unabhängige Reviewer.
- Blocker im Branch-Protection-Skript geschlossen: Eine bestehende Regel wird nie mehr überschrieben (GET-404-Ambiguität).
- Das Kernel-Gate erzwingt exakt einen Block und lehnt einen leeren Kanon ab.
- `trace`-Präzision: kein Bare-Number-Grep, leere Query wird verweigert.
- Der Ratchet ist einziger Owner mit allen 13 Modulen.
- README-/Update-Semantik-Kohärenz.

## v1.30.0 — Nachvollziehbarkeit als Werkzeug: `trace.py`

**Was sich ändert.** SP44 liefert `trace.py`: die ganze Geschichte eines Arbeitsstücks in einem Kommando.
- Quellen: Story, Issue (Snapshot offline zuerst, dann `gh`, sonst nur Ref), aktive/archivierte Pläne, Commits, geparste `REVIEW work=`-Attestierungen, Reports samt FINDINGs.
- Read-only, Core.
- Unerreichbare Quellen werden benannt statt still übersprungen.

Details: SP44

## v1.29.0 — Quick Wins „verlässlich + lesbar": `setup_branch_protection.sh`

**Was sich ändert.** SP43:
- `setup_branch_protection.sh` ist der eine Schritt, der aus „Gate läuft" „Gate blockt" macht, als idempotenter Einzeiler (nicht-destruktiv, ehrliche Fehlermodi für Private-Repo/Free-Plan).
- Die Actions-Job-Id ist von `gates` auf `process-gates` angeglichen, damit der dokumentierte Required-Check-Kontext überhaupt erfüllbar ist.
- Die SP-Historie ist aus dem README in dieses CHANGELOG ausgelagert.

Details: SP43

## v1.28.0 — Profile statt 13 Modul-Booleans, Härtungs-Ratchet

**Was sich ändert.** SP42 (Meta-Review „Reichweite vor Tiefe" für Solo-Devs/kleine Teams):
- **Profile** statt 13 Modul-Booleans: Eine `profile`-Frage (minimal/solo/team/custom) leitet den Modul-Default ab; explizites `modules` überschreibt weiter.
- Der **Härtungs-Ratchet** in start-here: Ein Modul wird eingeschaltet, wenn sein Trigger eintritt — erste Persistenz → security_floor, zweite Surface → parity usw. Lockern ist eine dokumentierte Prozessentscheidung.

Details: SP42

## v1.27.0 — Kernel überlebt Compaction

**Was sich ändert.** SP41:
- Eine selbst-heilende Direktive *im* Kernel-Block: Bei Resume/Compaction werden Kernel und Regeln neu gelesen. Sie ist byte-identisch in allen vier Kopien und damit vom Kernel-Gate unentfernbar.
- Phasen-Re-Hydration in `/execute`, `/review`, `/prime`.
- Ehrliche Grenze und Pro-Harness-Realität in start-here dokumentiert — ein Gate sieht den Live-Kontext nicht.

Details: SP41

## v1.26.0 — Kernel-Integrität als viertes Core-Gate: `check_kernel.py`

**Warum.** Ein abgeleiteter Prozess machte die Lücke „Regeln vergessen, weil ungegatet" sichtbar.

**Was sich ändert.** Der immer-geladene Regel-Block muss in jedem vorhandenen Anker byte-identisch zu `kernel.md` sein.

**Wirkung.** Eine still gelöschte oder geänderte Regel blockt den Merge.

Details: SP40

## v1.25.0 — 4-Perspektiven-Funktionsaudit: sbom-Gate gehärtet

**Was sich ändert.** SP39 (4-Perspektiven-Funktionsaudit):
- sbom-Gate gehärtet: SPDX-`OR`/`AND`-Auswertung, nur die Root-Komponente ist exempt, Multi-License-Konjunktion, exakte Coverage-Namen, kein doc-drift-Rotlauf beim frischen Render.
- `attention` zählt nur existierende Tests.
- DoR/DoD- und Tier-Routen-Kohärenz.
- `ARCHITECTURE-OVERVIEW.md` ist `.jinja`.
- BOOTSTRAP-`github_master`-Key.
- Interne Sprint-Refs aus Adopter-Code entfernt.

Details: SP39

## v1.24.0 — Bindende Definition of Ready & Done

**Was sich ändert.** SP38:
- Die bindende **Definition of Ready & Done** als Core-Doc `definition-of-ready-and-done.md`: pro Arbeitseinheit, Enforcement an bestehende Mechanismen delegiert, lebende Checklisten.
- Die Namens-Kollision mit der Projekt-Onboarding-Reife in `start-here.md` ist aufgelöst.
- In Brainstorm/Review, Regel 7 und Review-Checkliste eingehängt.
- Konsolidierung von Backport-Patch 0013.

Details: SP38

## v1.23.0 — Backport-Batch 2: Koordinations-Dashboards

**Was sich ändert.** SP37 (Backport-Batch 2):
- Read-only Koordinations-Dashboards unter `github-issues`: `who_is_working.py` (Nebenläufigkeits-Preflight) und `attention.py` (wo ein Mensch hinschauen sollte, inkl. Issue-Hygiene).
- Parallel-agents-Workflow-Abschnitt.
- Die label-mutierenden Lifecycle-Tools und die `status:hold`-/`awaiting-ack`-Overlays sind bewusst ausgelassen.

Details: SP37, #22

## v1.22.0 — Backport-Batch 1: pre-push prüft gepushte Commits, `sbom`-Modul

**Was sich ändert.** SP36 (Backport-Batch 1 aus dem parallelen Prozess-Zweig):
- pre-push prüft die **gepushten Commits** statt des Working Tree (Wegwerf-Worktree).
- Neues opt-in **`sbom`**-Modul mit CycloneDX-Lizenz-Attestierung.
- feature-registry-Advisory für unter-granulare Akzeptanz.

Details: SP36

## v0.1.0 – v1.21.0 — Sub-projects SP1 to SP35 · 2026-07-01 – 2026-07-07

**Was sich ändert.** SP1 bis SP35 sind bis `v1.21.0` ausgeliefert:
- SP1 (Foundation).
- SP2 (Architektur-Onboarding).
- SP3 (feature-registry, github-issues, contracts-drift).
- SP4 (git-hooks, contract-first, parity, security-floor).
- Capstone (command-adapters, `v1.0.0`): das volle Command-Set des Referenzprojekts, harness-nativ.
- SP7 (ci-adapters): GitLab CI und Install-Fallbacks.
- SP8 (english-canon): English-Canon und ehrliche Ökonomie.
- SP9 (audit-fixes): False-Greens geschlossen, Failure-Modes sprechen.
- SP10 (telemetry): GRADE-Trace und KPI-Cockpit, Effizienz messbar.
- SP11: Re-Audit und Public-Readiness.
- SP12 (verification-independence): Verifikation unabhängig, tier-gestaffelt.
- SP13 (anchor-guidance).
- SP14 (junior-legibility): Review-Checkliste, Tier-Erkennung.
- SP15 (arch-docs): arc42/C4-lite Architektur-Doku-Modul.
- SP16 (review-breadth): Performance-/Observability-Dimensionen.
- SP17 (parallel-friction): Journal-Sharding, Parallel-efforts-Doku.
- SP18 (decision-records): getyptes Decision Record und Core-Integritäts-Gate.
- SP19 (review-enforcement): Review-Unabhängigkeit als gegatete Attestierung.
- SP20 (issue-centricity): Issue-before-code für Tier 3+, geschärfte Claim-Disziplin.
- SP21 (dependency-sequencing): `blocked_by`, Zyklus-Gate und ready-order-Tool.
- SP22 (github-master): Issues als SSOT über hermetischen Snapshot-Gate und Sync.
- SP23 (sub-issues): `parent`-Dekomposition, Zyklus-/Drift-Gate, Hierarchie-View.
- SP24 (project-board): hermetischer Spalten-Konsistenz-Gate und Board-Automation.
- SP25 (github-master honesty-pass): Freshness-Disclosure und ehrliche Doc-Fixes.
- SP26: Rule-5-Konsolidierung — increment-vs-rewrite-Entscheidung und Gate-Refactor.
- SP27 (story-lifecycle-closure): done braucht hart ein Issue, DoR/DoD-View, Discovered-work-Inbox.
- SP28 (audit-hardening): sechs Persona-Audits über zwei Modelle — zwei Live-Bugs gefixt, Konsens-Findings ausgeräumt, verifizierte Zweige regressionsgesichert.
- SP29 (tier-model): Die Skala ist von 0–4 auf zero-based **0–3** kollabiert. Das unter PR/Merge-Pflicht faktisch fiktive Tier 0 „direct commit" ist in Tier 1 gefaltet; jede verbleibende Grenze trägt Gewicht; Gate-Schwellen und Anchor/Doku sind remapped.
- SP30 (decision-flow-wiring): Decision Records sind in die Phasen eingehängt — Brainstorm liest sie als Constraints, Plan nennt seinen Decision-Kontext, Execute stoppt bei entdeckter Grundsatzentscheidung, die Review-Checkliste fragt nach fehlendem, widersprochenem oder still-obsoletem Record.
- SP31 (product-frame): `PRODUCT.md` als **Core**-Artefakt — Produktrahmen mit Goals/Non-Goals/Constraints, im Init-Dialog erstellt, von allen Phasen als Richtungs-Constraint gelesen, immer aktives Gate: fehlend hart, not-onboarded ehrliche Note, Platzhalter-nach-Onboarding und tote Refs hart.
- SP32 (review-visibility): Audits/Reviews samt Prompt, Verdikt und Findings als Report-Artefakt und GitHub-Issue — `FINDING`-Grammatik, `publish_review.sh` mit Kampagnen-Bündelung unter Parent-Issue, hermetische Bindung (unpubliziert ohne Waiver hart, Follow-up-Finding ohne Issue hart, gesplittete Kampagne hart). Entdeckte Arbeit in korrekter Form: `finding`-/`bug`-Templates mit EARS-AKs und Origin-Sektion, Rückverlinkung und Kommentar am Ausgangsitem als Konvention.
- SP33 (gate-hardening aus 4-Session-Audit): 8 reproduzierte Gate-Defekte geschlossen — Tier-Range-Validierung, Report-Header-Split auf jeder Ebene, geteilte Fence-/Bullet-Disziplin für REVIEW/GRADE, Decisions-Sektionsparser, github-master fail-clean, Kampagnen-Ref-Normalisierung, Symbol-Wortgrenze, code_roots-Skalar. Dazu der Patch `v1.20.1` aus dem SP33-Review: Unicode-Ziffer-Crash im Tier-Check, Header-Split auf jeden Überschriften-Stil, ehrliche Symbol-Grenze.
- SP34 (flow-closure): Plan-Archivierung als benannter Merge-Schritt, Baseline-Commit-Bypass, tracker-lose Waiver für done-Story und Follow-up-Finding, neutrale `kernel.md`, Reviewer-Grammatik im `/review`, geschärfte Tier-1/2-Grenze und Tier-0-1 als Self-Check-Band.
- SP35 (economics/discoverability): Der Anchor listet aktive Modul-Docs, `/quick` trägt eigene Schritte, `/prime` liest inbox, Which-artifact-when-Router, Multi-Agent-SSOT-Ehrlichkeit, Mid-Size-Trap benannt.

Details: SP1–SP35
