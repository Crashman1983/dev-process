# SP54 — Review-Artefaktbindung und Governance-Pilot

**Status:** Entwurf zur schriftlichen Freigabe

**Datum:** 2026-07-18

**Scope:** aktiver Review-Integritaetsslice plus nicht-aktiver Governance-Pilot

**Risiko:** Tier 2 — Core-Gate, Review-Grammatik und Pre-Push-Verhalten

## Ausgangslage

Die Kenni-Neuausrichtung hat zwei voneinander verschiedene Probleme sichtbar
gemacht:

1. Ein fachlich wichtiger, aber technisch rein dokumentarischer Auftrag lief
   durch einen unverhaeltnismaessig grossen Plan-, Telemetrie- und
   Review-Apparat.
2. `dev-process` attestiert heute Unabhaengigkeit und Modellfamilie eines
   Reviews, bindet das `pass` aber nicht mechanisch an den tatsaechlich
   gemergten Diff.

Der zweite Punkt ist bereits ein konkreter Integritaetsfehler und wird in SP54
aktiv behoben. Der erste Punkt wird als messbarer Pilot festgehalten, aber noch
nicht in das allgemeine Routing des Templates eingebaut: Das bestaetigte
Kenni-Design verlangt drei reale Anwendungen, bevor aus dem Overlay eine
portable Standardregel wird.

## Verifizierter Ist-Stand

- `make_review_bundle.py` nennt heute nur den symbolischen Base-Ref und die
  Anzahl der Diff-Zeilen. Es gibt weder aufgeloeste Base-/Head-SHAs noch einen
  Fingerprint.
- Die `REVIEW`-Grammatik prueft `work`, `tier`, Reviewer, Modell,
  Independence, Verdict und Runde, aber kein Artefakt.
- Das Review-Ergebnis wird im getrackten Journal abgelegt. Wird diese Zeile
  erst nach dem Review committed, veraendert die Attestierung selbst den Diff,
  den der Reviewer gesehen hat.
- Der Pre-Push-Hook kennt Local- und Remote-SHA bereits aus Gits
  vierfeldrigem Push-Protokoll, reicht die Remote-Basis aber noch nicht an die
  Core-Gates weiter.
- Die eigenen Prozessgates laufen bereits korrekt per `uv` in einem
  temporaeren Detached-Worktree. Fuer zusaetzlich eingebundene Projektgates
  fehlt noch die gleich starke, ausdrueckliche Portabilitaetsanforderung.

## Ziele

- Ein Tier-2+-Review kann nur den exakt zertifizierten Branch-Diff freigeben.
- Der Push beziehungsweise Pull-Request nach `main` blockiert, wenn der seit
  der Integrationsbasis uebertragene Diff nicht dem Review-Zertifikat
  entspricht.
- Die Attestierung veraendert den reviewten Tree nicht.
- Bestehende historische `REVIEW`-Zeilen bleiben lesbar und werden nicht durch
  eine rueckwirkende Migration rot.
- Neue Plaene koennen die strenge Bindung explizit und maschinenlesbar
  verlangen.
- Der Governance-Pilot dokumentiert Auftragsmodus, Mutationsklasse,
  Claim-Delta, Endzustand und Prozesskosten fuer drei reale Anwendungen.
- Projektgates sind aus einem frischen Worktree reproduzierbar oder deklarieren
  ihren Bootstrap explizit.

## Nicht-Ziele

- Keine Aktivierung eines allgemeinen `governance-only`-Routings vor den drei
  Kenni-Pilotfaellen.
- Keine Kenni-Pfade, Claude-spezifischen Regeln oder Produktentscheidungen im
  neutralen Template.
- Kein Signatur- oder Trust-System fuer die Wahrheit der Reviewer-Identitaet;
  diese bleibt attestiert.
- Kein Workflow, der automatisch merged oder pusht; die vorhandenen
  Read-only-CI-Gates werden lediglich mit der Kandidatenbasis versorgt.
- Kein stilles Wiederverwenden eines Reviews nach einem Rebase. SP54 verlangt
  den Review nach dem finalen Rebase. Ein spaeteres Rebind-Protokoll darf nur
  eingefuehrt werden, wenn es die Diff-Gleichheit maschinell beweist.

## Bewertete Ansaetze

### A — Nur Dokumentation

Der Workflow fordert einen manuellen Hashvergleich vor dem Merge.

**Vorteil:** klein und migrationsfrei.

**Nachteil:** weiterhin nicht gegatet; ein Agent kann Review A dokumentieren
und Diff B pushen. Verworfen.

### B — Fingerprint als zusaetzliche Journalfelder

`base`, `head` und `diff` werden an die heutige Journalzeile angehaengt.

**Vorteil:** geringe Parseraenderung.

**Nachteil:** selbstreferenziell, weil das Committen der Zeile den reviewten
Diff nachtraeglich veraendert. Verworfen.

### C — Leeres Review-Zertifikats-Commit plus Push-Bindung

Der Reviewer sieht den finalen Tree einschliesslich archiviertem Plan. Das
Ergebnis wird danach ausschliesslich im Body eines leeren Commits gespeichert.
Das Commit hat denselben Tree wie sein Parent. Beim `main`-Push vergleicht das
Core-Gate den binaren Diff vom Remote-SHA zum Push-Tip mit dem zertifizierten
Hash.

**Vorteil:** keine Selbstreferenz, exakter Merge-Kandidat, portable Git-
Semantik, fail-closed am entscheidenden Push.

**Nachteil:** ein zusaetzliches leeres Metadaten-Commit und eine neue gebundene
Grammatik. **Gewaehlter Ansatz.**

## Architektur

### 1. Kanonischer Review-Fingerprint

`make_review_bundle.py` loest vor dem Bundling drei Werte auf:

```text
base=<merge-base SHA>
head=<reviewter HEAD SHA>
diff=<sha256 von git diff --binary base...head>
```

Der Hash wird ueber die exakten Bytes des `git diff --binary`-Outputs
berechnet. Das Bundle zeigt alle drei Werte in einem maschinenlesbaren
Abschnitt und importiert weiterhin die Ausgabegrammatik aus `check_review.py`.

Der Plan muss vor dem Bundle finalisiert und archiviert sein. Dadurch sind
Planinhalt und Archivstatus Bestandteil des reviewten Diffs.

### 2. Gebundene REVIEW-v2-Attestierung

Neue gebundene Records erweitern die bestehende Zeile um:

```text
base=<40-oder-64-stellige Git-SHA>
head=<40-oder-64-stellige Git-SHA>
diff=<64-stelliger SHA-256>
```

Ein Plan fordert diese Form mit:

```text
review-binding: artifact-v1
```

Historische Plaene ohne dieses Feld und historische Journalzeilen mit der
bisherigen Grammatik bleiben gueltig. Ein Plan mit `artifact-v1` kann jedoch
nur durch einen gebundenen Record freigegeben werden.

### 3. Zertifikats-Commit ohne Tree-Mutation

Nach dem externen Review wird der exakte `REVIEW`-Record in den Body eines
leeren Commits geschrieben. Das Gate akzeptiert ein Zertifikat nur, wenn:

- der Record aus einer Commit-Message stammt, nicht nur aus dem Journal;
- der Zertifikats-Commit genau einen Parent besitzt;
- dieser Parent dem Feld `head` entspricht;
- Zertifikats-Tree und Parent-Tree identisch sind;
- `base` und `head` als Commits im Repository aufloesbar sind;
- der neu berechnete binaere Diff-Hash `diff` entspricht.

Journalzeilen bleiben der menschenlesbare Verlauf, sind fuer
`review-binding: artifact-v1` aber kein ausreichendes Zertifikat.

### 4. Bindung an den tatsaechlichen Integrationskandidaten

`run_hook.py` reicht bei einem Push nach `main`/`master` den Remote-SHA und
Remote-Ref als Umgebungsvariablen an den Gate-Runner im temporaeren Worktree
weiter. Die GitHub- und GitLab-CI-Adapter setzen dieselbe neutrale
Kandidatenbasis aus ihrem Pull-/Merge-Request- beziehungsweise Push-Event.
Beide CI-Adapter holen die vollstaendige Git-Historie, damit Base, reviewter
Head und Zertifikats-Commit wirklich aufloesbar sind.

`check_review.py` betrachtet dann nur neu archivierte, gebundene Plaene im
Diff `candidate_base...HEAD`. Der Variablenname und die Gate-Logik bleiben
providerneutral; GitHub-/GitLab-Ausdruecke leben ausschliesslich in den
jeweiligen CI-Adaptern.

Fuer genau einen solchen Merge-Slice muss ein passendes Zertifikat existieren,
und

```text
sha256(git diff --binary remote_sha...HEAD) == REVIEW.diff
```

gelten. Das leere Zertifikats-Commit aendert diesen Tree-Diff nicht. Mehrere
unabhaengige, reviewte Slices in einem einzigen `main`-Push werden bewusst
nicht erraten; sie sind nacheinander zu pushen oder brauchen spaeter ein
explizites Batch-Zertifikat.

Bei neuen Feature-Branch-Pushes, geloeschten Refs und historischen lokalen
Laeufen ohne Kandidatenbasis greift weiterhin die bisherige Presence-/
Arithmetic-Pruefung. Ein CI-Adapter, der einen gebundenen Merge pruefen soll,
muss die Kandidatenbasis liefern; fehlt sie dort, blockiert der gebundene Plan
statt eine nicht beweisbare Freigabe zu behaupten.

### 5. Governance-Oekonomie als nicht-aktiver Pilot

Eine Meta-Repo-Pilotdatei erfasst drei Kenni-Anwendungen mit demselben Schema:

- `intent_mode`: decision-only, documentation, planning oder implementation;
- `semantic_impact`: niedrig, mittel, hoch;
- `mutation_class`: mechanical-docs, governance-only oder runtime;
- Owner, Non-goals, erlaubte Pfade und erwarteter Endzustand;
- Claim-Delta fuer neue Ist-, Sicherheits-, Vollstaendigkeits- und
  Paritaetsaussagen;
- Laufzeit, Planzeilen, Commitanzahl, Reviewrunden, gefundene Claim-Fehler,
  Eskalationen und Tool-Stalls;
- ob eine bereits beantwortete Produktentscheidung erneut abgefragt wurde;
- Ergebnis `adopt`, `revise` oder `reject` nach Fall 3.

Diese Datei ist Evidenz fuer eine spaetere Entscheidung, keine aktive
Template-Regel. Der erste Kenni-Fall wird als `1/3` eingetragen.

### 6. Fresh-Worktree-Vertrag fuer Projektgates

`testing.md` und die Git-Hook-Moduldokumentation stellen klar:

- Ein Pre-Push-/CI-Gate muss in einem frischen Checkout ohne lokale `.venv`,
  `node_modules` oder andere ignorierte Caches starten koennen.
- Abhaengigkeiten werden durch ein deklariertes, reproduzierbares Kommando
  bereitgestellt, beispielsweise `uv run`, einen Lockfile-basierten
  Package-Manager oder einen Container.
- Ein Gate darf fehlende lokale Caches nicht mit einem Produktfehler
  verwechseln.
- Kann ein projektspezifisches Gate diese Bedingung nicht erfuellen, darf es
  nicht kommentarlos in den portablen Pre-Push-Pfad aufgenommen werden.

Das bestehende `uv`-/Detached-Worktree-Verhalten bleibt Owner; es entsteht kein
zweiter Hook-Runner.

## Fehlerverhalten

- Unaufloesbare SHAs, falsche Hashlaenge oder unbekannte Zusatzfelder: hartes
  Grammar-/Binding-Failure.
- Diff stimmt nicht: harter Block mit erwarteter und tatsaechlicher Digest.
- Zertifikats-Commit ist nicht leer oder nicht direkter Kind-Commit des
  reviewten Heads: harter Block.
- Gebundener Plan besitzt nur eine Legacy-Journalzeile: harter Block.
- `main` hat sich nach dem Review bewegt: Fetch/Rebase/Re-Gate, dann neuer
  Review. Keine automatische Review-Wiederverwendung in SP54.
- Kein Push-Kontext: ehrliche Presence-Pruefung ohne falsche Kandidatenzusage.
- Projektgate benoetigt einen lokalen Cache: klare Bootstrap-/Portabilitaets-
  Meldung statt `--no-verify` als Normalweg.

## Tests

1. Bundle enthaelt aufgeloeste Base-/Head-SHAs und reproduzierbaren SHA-256.
2. Eine Inhaltsaenderung nach dem Bundle erzeugt einen anderen Hash.
3. Legacy-Records bleiben parsebar und klaeren Legacy-Plaene.
4. `artifact-v1` akzeptiert keinen Legacy-Record.
5. Ein korrektes leeres Zertifikats-Commit klaert den gebundenen Plan.
6. Nicht-leeres Zertifikat, falscher Parent, unbekannte SHAs und falscher Hash
   blockieren.
7. Pre-Push reicht die Remote-Basis nur fuer `main`/`master` weiter.
8. Der Main-Push blockiert, wenn Push-Diff und Zertifikat auseinanderlaufen.
9. Feature-Branch-Pushes bleiben vor dem Merge reviewfrei moeglich.
10. Gerenderte Test-/Hook-Dokumentation traegt den Fresh-Worktree-Vertrag und
    bleibt harness-neutral.
11. Die Pilotdatei enthaelt alle Messfelder, aktiviert aber weder Risk-Tier-
    Routing noch einen neuen Command.
12. Vollstaendiger Template-Render und die bestehende Suite bleiben gruen.

## Geplante Dateien

- `template/scripts/process/make_review_bundle.py`
- `template/scripts/process/check_review.py`
- `template/scripts/process/{% if modules.git_hooks %}run_hook.py{% endif %}`
- `template/.github/{% if ci.github %}workflows{% endif %}/process-gates.yml.jinja`
- `template/{% if ci.gitlab %}.gitlab{% endif %}/ci/process-gates.gitlab-ci.yml`
- `template/docs/process/verification-independence.md`
- `template/docs/process/journal-state-plans.md`
- `template/docs/process/workflow.md.jinja`
- `template/docs/process/testing.md`
- `template/docs/process/{% if modules.git_hooks %}modules{% endif %}/git-hooks.md`
- `tests/test_review_bundle.py`
- `tests/test_review.py`
- `tests/test_git_hooks.py`
- `tests/test_ci_adapters.py`
- `docs/pilots/2026-07-18-governance-economics.md`

## Rollout und Erfolgskriterien

SP54 ist erfolgreich, wenn ein gebundener Tier-2+-Plan nicht mehr mit einem
anderen als dem reviewten Diff nach `main` gepusht oder per Pull-/Merge-Request
integriert werden kann, historische Adopter keinen rueckwirkenden roten
Gate-Zustand erhalten und die Hooks weiter aus einem frischen Worktree laufen.

Der Governance-Teil gilt erst nach drei echten Kenni-Faellen als
entscheidungsreif. Danach folgt ein eigener Designentscheid zwischen engem
Overlay und vollstaendigem `Impact x Mutation`-Modell. Bis dahin veraendert der
Pilot das Template-Routing nicht.

## Anchor Delta

- Core-Owner: `verification-independence.md`, `journal-state-plans.md` und
  `check_review.py` werden gemeinsam erweitert.
- Workflow-Adapter: `workflow.md.jinja` beschreibt Finalisierung, Review und
  leeres Zertifikats-Commit.
- Hook-Owner: `run_hook.py` traegt nur Push-Kontext; `gate_runner.py` bleibt
  Gate-Registry-Owner.
- Risk tiers, Produktframe, Contracts, Feature Registry und optionale Module
  bleiben unveraendert.

## Feature Registry Trace

Template-Selbstveraenderung; die Render- und Gate-Tests sind die
Akzeptanzbeweise. Es entsteht keine Produkt-Story und keine Runtime-Funktion in
einem gerenderten Zielprojekt.
