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

- **D1 Ein Owner für Codex-Worker (P6).** `scripts/process/_dispatch_codex.py` kommt aus Kenni, ohne `legacy_preflight` und ohne Kenni-Namen (Client-Name `dev-process-dispatch`).
  - **Wann es gilt:** wenn ein Lauf mit `--harness codex` startet. Für einen solchen Lauf wird die CLI-Form geprüft (`executable`) und der Katalog abgefragt (`probe`: Login, Provider, Modell, Effort). Es gibt kein stilles Ersatzmodell. Der Lauf ist detached mit Supervisor, Zeitlimit und Belegen.
  - **Was nicht angefasst wird:** Eine `codex`-Zelle in der normalen Policy, etwa das Tier-3-Review aus dem `model-policy.json`-Kommentar, bleibt beim heutigen einfachen Runner. Der Steward attestiert sie wie heute aus dem Log. `tower.md` empfiehlt dafür die Variante. So bricht keine bestehende Zelle.
  - **Voraussetzungen der CLI:** `codex exec` mit `--output-schema` und `-o`, `codex app-server --stdio`, der OpenAI-Provider ohne Profil und ohne eigenen Endpunkt. Getestet mit CLI 0.154.0. Fehlt etwas davon, verweigert der Probe mit Grund, und es gilt D4.
- **D2 `--harness codex` und die Variante (P5, P12).**
  - `start`, `queue add` und `policy` nehmen `--harness claude|codex`.
  - Die Variante liegt in `docs/process/model-policy.codex.json` (Template-Datei). Projektwerte stehen in `docs/process/model-policy.codex.local.json`, das wie die Claude-Überlagerung Mapping für Mapping darübergelegt wird: Modellnamen, Zeitlimits, `context_sources`. Die Claude-Überlagerung gilt für die Variante nicht.
  - `model-policy.codex.json` und `model-policy.codex.local.json` kommen zu den Gate-Dateien in `check_review` (R2-F9).
  - Geprüft wird nach dem Zusammenlegen:
    - Die Variante ist vollständig, `detached`, ohne `decision_channel` und ohne `CLAUDE*`-env.
    - Jedes Modell der Variante hat eine Klasse in `review_evidence` (`families` oder `ranks`), sonst verweigert `start`. So scheitert ein Plan-Review nicht erst beim Attest. Geprüft wird am Arbeitsbaum. attest liest `review_evidence` an der Basis; eine Abweichung fängt dann attest (R2-F11).
  - Die Wahl reist durch Queue und Kette.
  - Das Template liefert Kennis Modellnamen als Vorgabe (`gpt-6-luna|sol|astra`). Der Probe verweigert ein unbekanntes Modell und nennt die verfügbaren.
  - Zeitlimits sind Policy-Schlüssel: `review_timeout_minutes` (Vorgabe 15) und `timeout_minutes` (Vorgabe 120).
- **D3 Vom Rat zum Attest in einem Schritt (Umkehr von Kennis Design; P1–P4).**
  - **Schema (P2, P3, R2-F4):** `verdict` (pass|block). `findings` als Objekte `{sev, action, kind, issue, title}` in der Grammatik von `check_issues`; ein `follow-up` ohne `issue` wird bei `handoff` verweigert. `criteria` als Zeilen `AC-<id>: <path>::<test>`, `unproven` oder `struck`. `refute` als Zeilen `survives: …` oder als Befund. `criteria` und `refute` sind beim Plan-Review leer. `refute` ist Pflicht, wenn das Bundle Gate-Code enthält.
  - **Prompt:** Er verlangt bei Gate-Code den Angriff nach `refute.md`. attest.py, git und REVIEW-Zeilen bleiben verboten.
  - **Plan-Review-Bundle (P4):** `prepare_review` übergibt die Plan-Slugs, die `prompt_for` schon auflöst, dazu `--plan-review`. Epic-Pläne (#204) gehen nicht verloren.
  - **`dispatch.py handoff <branch>` (P1, R2)** liest zuerst `handoff.json`. Ein schon erledigter Lauf wird nicht noch einmal behandelt. Dann prüft es wie bei Kenni Exit-Beleg, Schema, Invocation, Base/Head/Diff und Digests und attestiert im selben Schritt, im Worktree des Workers (`rec["worktree"]`):
    1. **Unabhängigkeit (R2-F5):** Sie ergibt sich aus dem Vergleich mit dem implementierenden Modell, das in den `pushed`-Berichten der Arbeit steht (`model_class`). Eine andere Familie ergibt `cross-model`. Dieselbe Familie ergibt `single-family`; dann braucht es eine committete Skip-Zeile, sonst verweigert `handoff`.
    2. **Bericht:** `.process-work/reviews/<datum>-<work>-codex.md`, mit Kopf (`review:`, `work: #N`, `publish-waived: <Grund>`, Modell, Invocation, Base/Head, `codex-result: <sha256>`), `FINDING`-Zeilen und den `AC`-Zeilen.
    3. **Refute bei Gate-Code (R2-F1):** Bei Tier 2 kommt Codex' `refute` als `REFUTE`-Zeile in den Bericht. Er zählt dort, weil er `cross-model` ist und Tier < 3 gilt. Bei Tier 3 schreibt `handoff` nichts in den Plan, denn dort muss ein getrennter Refute-Lauf schon eine Zeile im Plan haben (`refute.md`). Fehlt sie, verweigert attest, und es greift Schritt 4. Ob es Gate-Code ist, entscheidet dieselbe Regel wie im Attest (`attest_evidence._changed` und `check_review.is_gate_path`). Sie wird schon bei `start` angewandt, damit Prompt und Schema `refute` verlangen.
    4. **Probe-Lauf und Rückbau (R2-F3):** Zuerst läuft `attest.py --dry-run`. Verweigert er, löscht `handoff` den Bericht, schreibt die Gründe nach `handoff.json` und berichtet `blocked` mit diesen Gründen. Der Worktree bleibt sauber.
    5. **Attest (R2-F8):** `attest.py` aus dem Haupt-Checkout (der Branch unter Review schwächt sein eigenes attest nicht), mit dem Worktree als `root`: `--work <id> --tier <t> --model <modell> --independence bundle,non-implementing,<cross-model|single-family> --verdict <verdict aus dem Schema> --base … --head … --with <bericht> [--plan-review] --commit`.
    6. **Push (R2-F2):** `git push origin <branch>` aus dem Worktree. Der pre-push-Hook gilt. Verweigert er den Push, kommt das nach `handoff.json` und wird gemeldet.

    attest.py bleibt der einzige Schreiber von REVIEW-Zeilen, und alle Nachweisregeln aus v2.71 gelten. Zwischen Prüfung und Attest gibt es keine Lücke, in der jemand Bericht oder Urteil ändert.
  - **Epics (R2-F7):** Ist mehr als ein Plan fällig, verweigert ein Codex-Plan-Review mit Hinweis auf je einen Lauf pro Plan. Das ist eine benannte Grenze dieses Release.
  - **Restgrenze (benannt):** Wer attest.py von Hand mit einem selbst geschriebenen Bericht aufruft, umgeht `handoff`. Das ist das Bedrohungsmodell des ganzen Prozesses (Versehen, kein Angreifer), und `verification-independence.md` sagt es.
  - **Kette:** Nach erfolgreichem `handoff` berichtet dispatch `review-pass` oder `blocked` für den Worker. Danach geht die Kette weiter wie bei Claude-Reviews. Ein terminaler Codex-Lauf hält keinen `max_workers`-Platz (P10).
- **D4 Ausweg ohne Codex (P7, P10).**
  - **Wann:** wenn der Probe verweigert oder der Lauf `failed`, `interrupted` oder ohne gültiges Schema endet. Eine leere oder ungültige Ausgabe wiederholt der Supervisor einmal selbst.
  - **Aufzeichnung:** dispatch schreibt eine Zeile mit eigener Id nach `<common-dir>/dispatch/codex/unavailable.jsonl`, mit Zeit, Issue, Phase, Modell, Head und Grund.
  - **Die Meldung nennt den Ausweg wörtlich:**
    1. Den Review mit `--harness claude` auf der Review-Zelle des Tiers starten.
    2. `skipped cross-model work=<id>: codex unavailable <row-id> — <grund>` committen, beim Plan-Review mit `work=<id>-plan`.
    3. Mit `single-family` attestieren.

    Das ist der Weg aus v2.71, jetzt mit dem aufgezeichneten Grund.
  - **Tower-Befunde (R2-F10):**
    - `codex-skip-unmatched`, Schwere niedrig: In aktiven Plänen nennt eine Skip-Zeile der Form `codex unavailable <row-id>` eine Row-Id, die auf diesem Host nicht aufgezeichnet ist. Ein anderer Host kann der Grund sein; der Befund sagt das.
    - `codex-block-overridden`: Er wird aus dem Journal allein berechnet. Eine REVIEW-Zeile `verdict=block` eines Codex-Modells auf Head X wird von einem Pass eines anderen Modells auf demselben Head X gefolgt.
  - Bei Kenni (Cross-Model ab Tier 2) gilt das ab Tier 2.
- **D5 `rehydrate --codex`.**
  - Port mit `--install` und `--check` für `.codex/hooks.json`, einer Obergrenze von 128 KB und vollem Kontext oder einem sichtbaren Abbruch, nie mit Teilkontext.
  - Quellen: Kernel, Pflichtregeln und die Codex-Policy. Dazu `AGENTS.md` oder `CLAUDE.md`, wenn vorhanden, und die Liste `context_sources` aus `model-policy.codex.json`; darüber nimmt Kenni sein Skill auf.
  - `.codex/` kommt in die `.gitignore` des Templates.
- **D6 Docs.**
  - `tower.md`: Abschnitt „Codex worker“ mit Auswahl, Probe, Supervisor, `list`/`stop`/`handoff`, Zeitlimits aus der Policy (Vorgabe: Review 15 Minuten, sonst 2 Stunden) und dem Ausweg.
  - `verification-independence.md`: Ein Codex-Review attestiert per `handoff` plus Steward. Der Satz „the end-to-end path with an attestation is Codex as a tool inside a Claude review“ entfällt.
  - `model-policy.json`-Kommentar: Verweis auf die Variante.
  - **Voraussetzung (Owner, 2026-10-15):** Eine installierte und eingeloggte Codex CLI auf dem Entwicklungshost ist Voraussetzung für Codex-Worker und Codex-Reviews. Sie steht in `docs/SYSTEM-REQUIREMENTS.md` (Upstream) und in `tower.md`, mit der Prüfung `dispatch.py start … --harness codex --dry-run` und dem Katalog-Probe. Ohne CLI gilt der Ausweg D4.

### E2 — Übergabe oder Kontext je Paket

- **D7 Text aus Kenni.**
  - `/plan` (`plan.md.jinja`) und `workflow.md`: Je größerem Paket steht eine Zeile `Execution: delegate | retain-context` mit einem Satz Begründung, nach Kennis Kriterien.
  - `/execute`: „Offload reading, never the change“ wird ersetzt durch „Decide handoff versus retaining context per coherent packet“. Bei `delegate` schreibt ein Subagent auf dem kleinsten passenden Modell auch Code. Er committet nie, die Session integriert und committet seriell. Ein größeres Modell braucht einen benannten Grund.
  - Das `[P]`-Protokoll bleibt.
  - `tower.md`: „Handoff is separate from model selection“, ohne Kenni-Modellnamen.
- **D8 Messung je Paket (P9).** `report.py` nimmt optional `--execution delegate|retain-context`. `process_kpis.py execution` gruppiert die schon gemessenen Review-Runden und Fix-Streaks nach Modus. Ohne solche Berichte sagt es, dass noch nichts gemessen ist. Kein Gate liest die `Execution:`-Zeile; sie ist Planinhalt, den das Plan-Review prüft.

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

1. **Paket A — Codex-Kern (D1, D2).** Port von `_dispatch_codex.py`, der `dispatch.py`-Hunks (`load_policy(harness)`, `start`, `list`, `stop`, Queue, Kette, CLI) und der Codex-Variante samt lokaler Überlagerung. Der Harness greift nur bei `--harness codex`. Tests aus Kennis `test_dispatch_codex.py` und `test_model_policy_codex.py`, ohne die Advisory-Pins. `Execution: retain-context`, weil der Port eng mit `dispatch.py` gekoppelt ist.
2. **Paket B — Bericht statt Rat (D3, D4).** Schema mit `criteria`, Bericht, attest-Befehl, Kette und `unavailable.jsonl`. Ein Ende-zu-Ende-Test mit Fake-`codex` auf dem PATH: handoff schreibt den Bericht, der gedruckte attest-Befehl geht durch, und ohne CLI entstehen die unavailable-Zeile und die Meldung. `Execution: retain-context`.
3. **Paket C — rehydrate und Docs (D5, D6).** Kennis `test_rehydrate_codex_process.py`, angepasst. `Execution: delegate`, weil die Entscheidungen feststehen und das Ergebnis per Test prüfbar ist.
4. **Paket D — Execution-Regel und Messung (D7, D8).** Text, `report.py`-Felder, `process_kpis execution`, Doc-Pins. `Execution: delegate`.
5. **Paket E — `ci.github: manual` (D9–D11).** Validator, Guards, Workflows, Docs. Tests: Render mit `manual` (nur Dispatch, kein Schutz-Skript, YAML gültig), mit `true` und `false` wie bisher, ein Validator-Fehler bei einem anderen Wert. `Execution: retain-context`.
6. **CHANGELOG, NEWS, Migration für Kenni.**

## Unabhängige Durchsetzung

`check_review`, `attest` und `attest_evidence` bleiben unverändert. Ein Codex-Pass erfüllt dieselben Nachweisregeln wie jeder andere: Bericht, AC-Zeilen, Refute bei Gate-Code und Klasse des Plan-Reviewers. Die Bindung an Base/Head kommt aus `handoff`. attest prüft die Head-Range wie bisher.

Ohne `--harness codex` ändert sich am Dispatch-Verhalten nichts, auch nicht für eine bestehende `codex`-Zelle in einer lokalen Policy (P6). `check_review` bekommt nur die zwei Codex-Policy-Dateien als Gate-Dateien dazu (R2-F9).

## Migration für Kenni

1. Vor dem Update `ci: {github: manual}` in `.copier-answers.yml` setzen.
2. Update auf das Release dieses Plans. Konflikte so lösen:
   - `.github/workflows/process-gates.yml`: die Template-Fassung übernehmen.
   - `dispatch.py` und `tower.md`: den neuen Render übernehmen. Kennis Modellnamen leben in `model-policy.codex.json`.
3. `scripts/process/dispatch.py` und `docs/process/tower.md` aus `.process-owned` streichen.
4. Kennis Advisory-Test (`test_codex_review_pass_darf_keine_chain_oder_train_freigabe_sein`) entfällt, weil der Owner anders entschieden hat. Die übrigen Codex-Tests sind Template-Tests. Die Legacy-Wrapper (`scripts/codex-*.sh`, `legacy_preflight`) bleiben bei Kenni.
5. Kennis Modellnamen, Zeitlimits und `context_sources` (mit Kennis Skill) kommen nach `model-policy.codex.local.json`.

## Plan-Review Runde 1 — Änderungen

Ergebnis: Block mit einem Blocker, sechs Majors und fünf Minors. Die Änderungen stehen oben in D1–D4 und D8:

- **P1 (Blocker):** Bindung und Attest kommen in einen Schritt (`handoff` attestiert im Worktree des Workers). Vorher hätte der Steward nach der Prüfung den Bericht oder das Urteil ändern können, und attest hätte die Bindung nie gesehen.
- **P2:** Für Gate-Code liefert das Schema `refute`. `handoff` hängt die REFUTE-Zeile an den Plan, und sie fährt `--with` mit.
- **P3:** Befunde sind Objekte in der Grammatik von `check_issues`, damit Report-Gate und `process_kpis rounds` sie lesen.
- **P4:** Das Plan-Review-Bundle bekommt die Plan-Slugs und `--plan-review`, statt nach der Issue-Nummer zu suchen.
- **P5:** `model-policy.codex.local.json` hält die Projektwerte, sonst wäre die Template-Datei wieder eine Eigen-Datei.
- **P6:** Der Harness gilt nur für `--harness codex`. Bestehende `codex`-Zellen der normalen Policy bleiben, wie sie sind. Mindestanforderungen der CLI sind genannt.
- **P7:** Ein Ausweg hinterlässt eine Row-Id. Zwei Tower-Befunde machen Skips ohne Aufzeichnung und übergangene Codex-Blocks sichtbar. „Stärkstes Claude-Modell“ ist ersetzt durch „Review-Zelle des Tiers“.
- **P8:** Die angebliche Warnung des Gate-Runners ist gestrichen, weil es sie nicht gibt. Restgrenzen bei `manual` sind `--no-verify` und der Merge-Button; `commits.md` und `start-here.md` nennen sie.
- **P9:** Die Messung ist auf `--execution` reduziert und nutzt vorhandene Kennzahlen.
- **P10:** Ein terminaler Lauf gibt seinen Platz frei. Die Wiederholung macht der Supervisor. Die Zeitlimits sind Policy-Schlüssel.
- **P11:** Tests ergänzt: Update von v2.72 mit `true` rendert byte-gleich, und ein String `"true"` wird verweigert. Letzteres steht im CHANGELOG.
- **P12:** `start --harness codex` verweigert ein Modell ohne Klasse in `review_evidence`.
- **Ablauf:** Paket E wurde vor dem Plan-Review begonnen (Commit ee80d88). Das Review fand daran nichts. Paket E bleibt, wie es ist, und wird mit P11 ergänzt.

## Plan-Review Runde 2 — Änderungen

Ergebnis: Block mit einem Blocker und fünf Majors. Die Mechanik von P1 trägt: `records_only`, die Berichtsfilterung und das Lesen am Head. Die Änderungen stehen oben in D2–D4:

- **R2-F1 (Blocker):** Bei Tier 3 ist der eigene Refute des Reviewers kein Plan-Refute. Bei Tier 2 steht er im Bericht, bei Tier 3 braucht es einen getrennten Lauf.
- **R2-F2:** `handoff` pusht den Attest-Commit; der pre-push-Hook gilt.
- **R2-F3:** Erst `attest --dry-run`, bei Verweigerung Rückbau und Bericht `blocked`.
- **R2-F4:** Der Bericht trägt `work:` und `publish-waived:` statt `issue:`. Befunde haben ein `issue`-Feld.
- **R2-F5:** `cross-model` wird aus der Familie des Implementierers abgeleitet, nicht behauptet.
- **R2-F6:** Paket A und „Unabhängige Durchsetzung“ sind an P6 angeglichen.
- **R2-F7:** Codex-Plan-Reviews für Epics sind eine benannte Grenze.
- **R2-F8:** attest läuft aus dem Haupt-Checkout mit dem Worktree als `root`. Gate-Code erkennt dieselbe Regel wie im Attest.
- **R2-F9:** Die Codex-Policy-Dateien sind Gate-Dateien.
- **R2-F10:** Die Tower-Befunde sind begrenzt; `codex-block-overridden` kommt aus dem Journal.
- **R2-F11:** Benannt: `start` prüft am Arbeitsbaum, attest an der Basis.
- **Umfang:** D5 (`rehydrate --codex`) bleibt drin. Kenni hat `rehydrate.py` gepatcht, ohne es als Eigen-Datei zu führen; das erzeugt sonst bei jedem Update Konflikte.

## Plan-Review Runde 3 — Änderungen

Ergebnis: Block mit zwei Majors und fünf Minors. Die Mechanik aus Runde 2 hält. Präzisiert wird:

- **R3-1 Keine Sackgasse nach Verweigerung:** Ein verweigerter `handoff` behält das geprüfte Codex-Ergebnis und steht auf `refused`, nicht auf erledigt. Wer danach eine Skip-Zeile oder einen REFUTE an den Plan anhängt (uncommittet im Worktree), ruft `handoff` erneut auf. Die Bindung lässt dann Änderungen nur an Plan-Dateien zu. Diese Pläne fahren `--with` mit, und attest prüft per `records_only`, dass dort nur Records angehängt sind.
- **R3-2 Familie definiert:** Alle `ranks`-Präfixe sind eine Familie, jedes `families`-Präfix eine eigene. `cross-model` gilt nur, wenn das implementierende Modell gemessen ist, eine bekannte Familie hat und diese sich von der des Reviewers unterscheidet. Gelesen wird der neueste Bericht des Issues auf diesem Branch (`pushed` beim Code-Review, `planned` beim Plan-Review), einschließlich der Berichte anderer Hosts über origin. Sonst gilt `single-family`. `--implementer <modell>` benennt das Modell von Hand.
- **R3-3 Ein Owner für die Skip-Pflicht:** `handoff` reicht nur das Token weiter. Ob eine Skip-Zeile nötig ist, entscheidet `attest --dry-run`.
- **R3-4 Benannt:** Gate-Code bei Tier 2, single-family geprüft, braucht einen REFUTE im Plan oder `skipped refute`. Der eigene Refute des Reviewers im Bericht zählt dann nicht.
- **R3-5 Kopf des Berichts:** `phase: plan` beim Plan-Review. `work:` trägt die Work-Id, und REFUTE-Zeilen nennen genau sie.
- **R3-6 Kein doppelter Attest:** Vor dem Attest sucht `handoff` im Journal eine REVIEW-Zeile mit derselben Work, demselben Modell und demselben Head. Findet es eine, gilt der Lauf als erledigt.
- **R3-7 Push verweigert:** `blocked` mit dem Hinweis, dass origin sich bewegt hat und der neue Head ein neues Review braucht.
