# Plan: Kenni-Rückport II

Datum: 2026-10-15 · Tier: 3 (Gate-Code: `dispatch.py`, neues `_dispatch_codex.py`, `rehydrate.py`, `report.py`, `process_kpis.py`, CI-Adapter, Copier-Frage) · Release: Update mit einem Migrationsschritt für Projekte, die `ci.github: manual` wollen

## Anlass

Der Owner hat am 2026-10-15 drei offene Punkte aus Rückport I entschieden. Alle drei kommen in ein Release:

- **E1:** Ein Codex-Review darf attestieren. Ist Codex nicht verfügbar, gibt es einen dokumentierten Ausweg, der eine Spur hinterlässt.
- **E2:** Kennis Regel „delegate | retain-context“ je Arbeitspaket wird übernommen, mit Messung je Paket.
- **E4:** `ci.github: manual` wird eine dritte Option. Kenni nutzt kein gehostetes CI (Kenni ADR-0069), und genau das muss funktionieren.

Die Codex CLI bleibt Voraussetzung auf dem Host. Portiert wird Kennis Code um die CLI herum: Start, Prüfung, Überwachung und Übergabe. Danach braucht Kenni `dispatch.py` und `tower.md` nicht mehr als Eigen-Dateien (`.process-owned`).

Bestandsaufnahme (Subagenten, Stichproben geprüft): Kennis `_dispatch_codex.py` (625 Zeilen), 374 Diff-Zeilen in `dispatch.py`, `rehydrate --codex`, `model-policy.codex.json` und etwa 40 Tests. Kenni hat den Harness bewusst nur beratend gebaut: `handoff` schreibt `advisory: true`, die Kette überspringt Codex-Reviews, und ein Kenni-Test pinnt das. Das Template sieht dagegen schon heute vor, dass der Steward das Review eines Nicht-Claude-Workers mit `--model <Zelle>` attestiert (`dispatch.prompt_for`, `attests=False`).

## Entscheidungen

### E1 — Codex als attestierbarer Reviewer

- **D1 Ein Owner für Codex-Läufe.** `scripts/process/_dispatch_codex.py` kommt aus Kenni, ohne `legacy_preflight` und ohne Kenni-Namen (Client-Name `dev-process-dispatch`). Es gilt für jede lokale Zelle, deren Befehlswort `codex` ist:
  - in der Codex-Variante (`--harness codex`);
  - in einer Codex-Zelle der normalen Policy, etwa dem Tier-3-Review aus dem `model-policy.json`-Kommentar.

  So gibt es einen Weg, wie Codex läuft, nicht zwei. Für eine Codex-Zelle gilt: Die CLI-Form wird geprüft (`executable`), der Katalog wird abgefragt (`probe`: Login, Provider, Modell, Effort), es gibt kein stilles Ersatzmodell, und der Lauf ist detached mit Supervisor, Zeitlimit und Belegen.
- **D2 `--harness codex` und die Variante.**
  - `start`, `queue add` und `policy` nehmen `--harness claude|codex`.
  - Die Variante liegt in `docs/process/model-policy.codex.json`. Sie ist vollständig, `detached`, hat keinen `decision_channel` und erbt kein `CLAUDE*`-env. Die lokale Claude-Überlagerung gilt für sie nicht.
  - Die Wahl reist durch Queue und Kette.
  - Das Template liefert die Variante mit Kennis Modellnamen als Vorgabe (`gpt-6-luna|sol|astra`). Der Katalog-Probe verweigert ein Modell, das die CLI nicht kennt, und nennt dabei die verfügbaren.
- **D3 Vom Rat zum Bericht (Umkehr von Kennis Design).**
  - **Schema:** `handoff <branch>` prüft wie bei Kenni Exit-Beleg, Schema, Invocation, Base/Head/Diff und die Digests von Bundle und Ausgabe. Das Schema bekommt `criteria`, ein Array von Zeilen `AC-<id>: <path>::<test>`, `AC-<id>: unproven` oder `AC-<id>: struck`. Beim Plan-Review ist das Array leer.
  - **Bericht:** Statt `advisory.json` schreibt `handoff` einen Review-Bericht nach `.process-work/reviews/<datum>-<work>-codex.md`. Er enthält eine Kopfzeile mit Modell, Invocation, Base/Head und Digests, je Fund eine `FINDING`-Zeile und die `AC`-Zeilen. Dazu gibt `handoff` den genauen attest-Befehl aus:
    - `--model <modell> --independence bundle,non-implementing,cross-model --base … --head … --with <bericht> --commit`;
    - beim Plan-Review zusätzlich `--plan-review`.
  - **Attest:** Der Steward führt den Befehl aus. attest.py bleibt der einzige Schreiber von REVIEW-Zeilen, und die Nachweisregeln aus v2.71 gelten unverändert. Der Codex-Prompt verbietet weiter attest.py, git und REVIEW-Zeilen, sagt aber nicht mehr „advisory“.
  - **Kette:** Ein Codex-Review wartet in der Kette, bis `handoff` gelaufen ist und der Steward `review-pass` oder `blocked` berichtet hat. Er wird nicht mehr übersprungen.
- **D4 Ausweg ohne Codex.**
  - Verweigert der Probe den Start oder endet der Lauf `failed`, `interrupted` oder ohne gültiges Schema, schreibt dispatch eine Zeile nach `<common-dir>/dispatch/codex/unavailable.jsonl`. Sie enthält Zeit, Issue, Phase, Modell und Grund.
  - Die Meldung nennt den Ausweg wörtlich:
    1. Den Review mit `--harness claude` starten, und zwar auf dem stärksten Claude-Modell.
    2. `skipped cross-model work=<id>: codex unavailable <datum> — <grund>` committen.
    3. Mit `single-family` attestieren.

    Das ist der bestehende Weg aus v2.71. Er bekommt jetzt den aufgezeichneten Grund dazu.
  - Bei Kenni (Cross-Model ab Tier 2) gilt das ab Tier 2.
  - Ein Leeroutput wird einmal wiederholt und gilt dann als nicht verfügbar. Das stammt aus Kennis `review.local.md` §4.
- **D5 `rehydrate --codex`.**
  - Port mit `--install` und `--check` für `.codex/hooks.json`, einer Obergrenze von 128 KB und vollem Kontext oder einem sichtbaren Abbruch, nie mit Teilkontext.
  - Quellen: Kernel, Pflichtregeln und die Codex-Policy. Dazu `AGENTS.md` oder `CLAUDE.md`, wenn vorhanden, und die Liste `context_sources` aus `model-policy.codex.json`; darüber nimmt Kenni sein Skill auf.
  - `.codex/` kommt in die `.gitignore` des Templates.
- **D6 Docs.**
  - `tower.md`: Abschnitt „Codex worker“ mit Auswahl, Probe, Supervisor, `list`/`stop`/`handoff`, Zeitlimits (Review 15 Minuten, sonst 2 Stunden) und dem Ausweg.
  - `verification-independence.md`: Ein Codex-Review attestiert per `handoff` plus Steward. Der Satz „the end-to-end path with an attestation is Codex as a tool inside a Claude review“ entfällt.
  - `model-policy.json`-Kommentar: Verweis auf die Variante.
  - **Voraussetzung (Owner, 2026-10-15):** Eine installierte und eingeloggte Codex CLI auf dem Entwicklungshost ist Voraussetzung für Codex-Worker und Codex-Reviews. Sie steht in `docs/SYSTEM-REQUIREMENTS.md` (Upstream) und in `tower.md`, mit der Prüfung `dispatch.py start … --harness codex --dry-run` und dem Katalog-Probe. Ohne CLI gilt der Ausweg D4.

### E2 — Übergabe oder Kontext je Paket

- **D7 Text aus Kenni.**
  - `/plan` (`plan.md.jinja`) und `workflow.md`: Je größerem Paket steht eine Zeile `Execution: delegate | retain-context` mit einem Satz Begründung, nach Kennis Kriterien.
  - `/execute`: „Offload reading, never the change“ wird ersetzt durch „Decide handoff versus retaining context per coherent packet“. Bei `delegate` schreibt ein Subagent auf dem kleinsten passenden Modell auch Code. Er committet nie, die Session integriert und committet seriell. Ein größeres Modell braucht einen benannten Grund.
  - Das `[P]`-Protokoll bleibt.
  - `tower.md`: „Handoff is separate from model selection“, ohne Kenni-Modellnamen.
- **D8 Messung je Paket.**
  - `report.py` nimmt optional `--packet <id> --execution delegate|retain-context`, dazu `--questions N --rework N` und `--escalated <grund>`.
  - `process_kpis.py execution` zeigt je Modus die Zahl der Pakete, Median und Summe der Rückfragen und der Nacharbeit, die Eskalationen sowie die Review-Runden der zugehörigen Issues.
  - Ohne solche Berichte sagt der Befehl, dass noch nichts gemessen ist.
  - Kein Gate liest die `Execution:`-Zeile. Sie ist Planinhalt, den das Plan-Review prüft.

### E4 — `ci.github: manual`

- **D9 Drei Werte.**
  - `ci.github` nimmt `true`, `false` oder `manual`. Die Copier-Frage bekommt einen `validator`, und der Hilfetext nennt alle drei.
  - Bestehende Antworten `true` und `false` bleiben gültig. Es gibt keine `_migrations`.
- **D10 Was `manual` rendert.**
  - Die Workflows bleiben, laufen aber nur auf `workflow_dispatch`: `process-gates`, `owner-digest` und `process-kpis` (ohne cron).
  - `setup_branch_protection.sh` wird nicht gerendert.
  - Die Pfad-Guards prüfen `ci.github` (Workflows bei `true` und `manual`) und `ci.github is sameas true` (Schutz-Skript).
- **D11 Docs.**
  - `start-here.md`, `commits.md`, `git-hooks.md` und die Modul-Docs („in CI when a CI adapter is installed“) unterscheiden: Bei `manual` ist die Durchsetzung der pre-push-Hook eines Klons, und kein Dokument darf sich auf ein Workflow-Ergebnis berufen.

## Aufgaben

Die Pakete und ihre Ausführung:

1. **Paket A — Codex-Kern (D1, D2).** Port von `_dispatch_codex.py`, der `dispatch.py`-Hunks (`load_policy(harness)`, `start`, `list`, `stop`, Queue, Kette, CLI) und der Codex-Variante. Die Auslösung für jede `codex`-Zelle steckt in `start`. Tests aus Kennis `test_dispatch_codex.py` und `test_model_policy_codex.py`, ohne die Advisory-Pins. `Execution: retain-context`, weil der Port eng mit `dispatch.py` gekoppelt ist.
2. **Paket B — Bericht statt Rat (D3, D4).** Schema mit `criteria`, Bericht, attest-Befehl, Kette und `unavailable.jsonl`. Ein Ende-zu-Ende-Test mit Fake-`codex` auf dem PATH: handoff schreibt den Bericht, der gedruckte attest-Befehl geht durch, und ohne CLI entstehen die unavailable-Zeile und die Meldung. `Execution: retain-context`.
3. **Paket C — rehydrate und Docs (D5, D6).** Kennis `test_rehydrate_codex_process.py`, angepasst. `Execution: delegate`, weil die Entscheidungen feststehen und das Ergebnis per Test prüfbar ist.
4. **Paket D — Execution-Regel und Messung (D7, D8).** Text, `report.py`-Felder, `process_kpis execution`, Doc-Pins. `Execution: delegate`.
5. **Paket E — `ci.github: manual` (D9–D11).** Validator, Guards, Workflows, Docs. Tests: Render mit `manual` (nur Dispatch, kein Schutz-Skript, YAML gültig), mit `true` und `false` wie bisher, ein Validator-Fehler bei einem anderen Wert. `Execution: retain-context`.
6. **CHANGELOG, NEWS, Migration für Kenni.**

## Unabhängige Durchsetzung

`check_review`, `attest` und `attest_evidence` bleiben unverändert. Ein Codex-Pass erfüllt dieselben Nachweisregeln wie jeder andere: Bericht, AC-Zeilen, Refute bei Gate-Code und Klasse des Plan-Reviewers. Die Bindung an Base/Head kommt aus `handoff`. attest prüft die Head-Range wie bisher.

Ohne Codex CLI und ohne `--harness codex` ändert sich am Dispatch-Verhalten nichts. Die einzige Ausnahme ist eine bestehende `codex`-Zelle in einer lokalen Policy. Sie läuft jetzt über Probe und Supervisor statt über den einfachen detached-Runner. Das steht im CHANGELOG.

## Migration für Kenni

1. Vor dem Update `ci: {github: manual}` in `.copier-answers.yml` setzen.
2. Update auf v2.73.0. Konflikte so lösen:
   - `.github/workflows/process-gates.yml`: die Template-Fassung übernehmen.
   - `dispatch.py` und `tower.md`: den neuen Render übernehmen. Kennis Modellnamen leben in `model-policy.codex.json`.
3. `scripts/process/dispatch.py` und `docs/process/tower.md` aus `.process-owned` streichen.
4. Kennis Advisory-Test (`test_codex_review_pass_darf_keine_chain_oder_train_freigabe_sein`) entfällt, weil der Owner anders entschieden hat. Die übrigen Codex-Tests sind Template-Tests. Die Legacy-Wrapper (`scripts/codex-*.sh`, `legacy_preflight`) bleiben bei Kenni.
5. `context_sources` in `model-policy.codex.json` nimmt Kennis Skill auf.
