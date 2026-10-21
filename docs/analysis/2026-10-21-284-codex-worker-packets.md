# #284 — Gebundene Codex-CLI-Worker-Pakete (Upstream-PLAN)

Issue: Crashman1983/dev-process#284, `phase-of: #270` (nur Klassentransport). Branch: `codex/284-cli-worker-packets`. Base: `694d35b77b7bc3832c9ba402a3e4b83aa834b773`. Plan-Worker: Codex CLI `gpt-6-sol` / `medium`, beauftragter begrenzter Port eines bereits geprüften Vertrags. Tier: **3**. Status: PLAN, weder Upstream-Planfreigabe noch Code-/Releasefreigabe.

## Anlass, Platzierung und Grenze

Ein enger Codex-Auftrag kann im aktuellen generischen Dispatcher als ganze Execute-Phase mit breiter Commit-/Push-Anweisung starten; die vorhandene Klassenauflösung erreicht `start`/Queue nicht. Paketbindung, wirksame Modell-/Effort-Zelle, normale Approval-Prüferwahl und knapper Fortschritt gehören zu demselben Dispatcher→Codex-Supervisor-Vertrag. Das ist wegen Auftrags-/Berechtigungsgrenze, dauerhafter Queue/Receipts und Template→Projekt-Grenze Tier 3, unabhängig von der späteren Diffgröße. Die beabsichtigte Verbesserung ist generisch: Ein Projekt kann einen einzelnen entschiedenen Task statt einer ganzen Codex-Phase starten und den tatsächlichen Prozess beobachten, ohne dessen Review zu ersetzen.

Platzierung: `template/scripts/process/dispatch.py` besitzt Modus, Paketvalidierung, Policy, Queue, Prompt und Chain; `template/scripts/process/_dispatch_codex.py` besitzt Codex-argv-Verifikation, Katalogprobe, beaufsichtigten Kindprozess und Receipts. Tests gehören in das **Upstream-Root** `tests/`, Dokumentation in generische `template/docs/process/`-Seiten erst in der Codephase. Projektwerte bleiben im jeweiligen `docs/process/model-policy.codex.local.json`. Kein zweiter Owner, kein optionales Modul und keine lokale Template-Kopie. Dieses `docs/analysis/`-Dokument liegt außerhalb des auszuliefernden `template/`.

Nicht Teil dieser Phase sind #270-Usage/Liveness/Failed-Work sowie #141/#153, Main/Release/Deploy, Native-Proben, private Daten, Credentials, Profile, Konfiguration/Hooks oder Gate-Abschwächung. Keine Template-Datei, Tests oder Policy werden in dieser PLAN-Phase geändert. Bei einer tatsächlichen Denial: STOP, keine indirekte Ausführung und kein anderer Transport. Ein Infrastrukturfehler führt zu einem kompakten Handoff statt weiteren Experimenten.

## Quellenstand und Decisions

Verbindliche Quellen für diesen Port: lokaler eingefrorener Vertrag im Anhang, die sechs ACs des zugehörigen Projekt-Slices, dessen Plan/Tasks und die aktuelle R4-Aggregation. R4 prüfte den Projekt-PLAN auf Head `33e7057c7549b374f72353e7bed0e98359bf7b38` (semantischer Stand `ed42b8a92`) und lautet **PASS with residuals**. R1/R2/R3 bleiben historische BLOCKs. Die frische Opus-Review war PASS; die rohe Codex-Stellungnahme war BLOCK mit zwei Vorschlägen, die unabhängig mit 50/60 bewertet und als Residuen geführt wurden. Das ist weder Upstream-Review noch Code-/Release-Gate. Der Port übernimmt insbesondere: Fake-CLI beweist nur einen Supervisor-Versuch, nicht das Innenverhalten eines LLM; Prozess-Exit 0 kann mit einer blockierten Aufgabe zusammenfallen. Keine neue Sicherheitsgarantie wird behauptet.

- **DECISION 2026-10-21:** #284 ist `phase-of: #270` allein für Klassentransport; der vorhandene Dispatcher und Supervisor bleiben Owner. Grund: keine parallele Zustandsmaschine für Usage/Liveness/Failed-Work.
- **DECISION 2026-10-21:** Der Paketvertrag im Anhang wird als v1 gebunden; nur der Steward erzeugt nach Planreview einen Paketcommit. Grund: ein präziser, überprüfbarer Start statt impliziter Vollphase.
- **DECISION 2026-10-21:** `approval=automatic|never` ist eine explizite **Prüferwahl**, niemals Operationsfreigabe. `automatic` gilt für jedes sonst gültige Execute-Paket, auch `[read, edit, test]` bei verbotenen Git-/Report-/Netz-/externen Schreiboperationen sowie enges Report/Netz-Paket ohne Git. Keine Ableitung aus Enum-Namen. Grund: auch native Tests können den unveränderten workspace-write-Rand berühren.
- **DECISION 2026-10-21:** `--approve-for-me` ersetzt bei validiertem Paket mit `automatic` das Sandbox-Paar als alternative CLI-Form; keine gleichzeitige Form, kein Bypass/Profil/weiteres Root. Ein Reviewer prüft einzelne Anfragen und kann ablehnen. Grund: keine pauschale Freigabe.
- **DECISION 2026-10-21:** Generische Codex-Modell-IDs bleiben wie `template/docs/process/model-policy.codex.json`: Default Sol, Tier 0/1 Luna, Tier 2 Sol, Tier 3 Plan/Review Astra und Execute Sol; Klassen mechanical Luna/design Sol. Für **alle** wirksamen Zellen wird expliziter Effort geplant: Luna `low`, Sol/Astra `medium`. Beide generischen Command-Vorlagen transportieren `{effort}`. Lokale Modell- und Effort-Werte werden nicht aus einem Projekt in das Template kopiert. Fehlendes/ungeeignetes Effort, Modell oder Provider-Katalogeintrag verweigert ohne Ersatz. Grund: volle Zelle und bestehende Policy-Precedence erhalten.
- **DECISION 2026-10-21:** Die vorgegebene Sol/medium-Planroute und No-Astra sind Operatorentscheidungen dieses Auftrags, kein neuer generischer Astra-Guard. Eine spätere unabhängige Tier-3-Prüfung bleibt erforderlich. Grund: Modellwahl darf Tier und Reviewstärke nicht still ändern.
- **DECISION 2026-10-21:** `allowed_operations` bleibt sichtbarer Auftragsscope und Disjunktheitsprüfung, kein Predicate für Approval-Route in `_dispatch_codex.executable`. Falls der Parameter dort nicht für die argv-Form gebraucht wird, wird er konsistent weggelassen. Grund: keine Wiederkehr der widerlegten Enum-Policy.
- **DECISION 2026-10-21:** `terminal.json` ist Prozessbeleg, keine Task- oder Review-PASS-Aussage. `blocked`/`approval-route-missing` muss selbst bei Prozess-Exit 0 als Taskbefund sichtbar bleiben. Grund: R4-Residuum F2.
- **DECISION 2026-10-21:** Die bestehende `record_kind`/`uncleared_plans`/`plan_drift`-Clearance wird mit einem Paketcommit-Test geprüft. Schlägt sie fehl, ist das eine Upstream-Entscheidung vor Implementierung, keine versteckte Gate-Änderung. Grund: #284 erteilt keine Gate-Abschwächung.

## Vertrag: Paket, Start und Grenzen

Der **vollständige eingefrorene v1-Text** steht im Anhang dieses Plans. Für die Umsetzung gelten diese prüfbaren Invarianten:

1. Der Steward schreibt eine reguläre UTF-8-JSON-Datei `specs/<feature>/packets/<task_id>.json` mit maximal 16 KiB und committet **nur** diese Datei als Single-Parent-Commit. `source_head` ist exakt dessen Parent, `packet_head` der resultierende Commit und bewusst nicht in der Datei. Kein späterer Metadatencommit, Rebase oder bloße Ancestry genügt. Das offene Task-/Klassenpaar stammt aus dem unveränderten `tasks.md`-Blob auf diesem Commit.
2. Codex `execute` verlangt genau `--packet <relativer Pfad> --class <Klasse>` oder `--whole-phase`. Ohne Markierung, mit altem Codex-Execute-Queueeintrag oder impliziter Klasse wird verweigert. Whole-Phase bleibt ausdrücklich `standard` mit bisherigem Prompt und workspace-write-Sandbox; Claude-Starts bleiben kompatibel. Review erbt weder Execute-Klasse noch Approval.
3. Vor Sync wird `<packet_head>:<packet_path>` vom **Zielbranch** gelesen, nie `HEAD:` des Main-Checkouts. Nach `sync_worktree` und direkt vor `launch` stimmen Ziel-Worktree-HEAD, Git-Blob und Datei-Bytes exakt mit Paketcommit und Digest überein. Es gibt eine Invocation und einen Digest pro Lauf. Doppelte JSON-Schlüssel, unbekannte/fehlende Felder, falsche Phase/Klasse, Symlink/Pfadausbruch, Dirty-Datei, ungültiges UTF-8 und Drift verweigern vor Kindprozess mit Exit 3, ohne Fallback.
4. Pflichtfelder: `version=1`, `issue`, `branch`, `phase=execute`, `tier=0..3`, `task_id=T[0-9]{3,}`, `class`, `source_head`, `allowed_operations` (nichtleer/eindeutig), `forbidden_operations` (eindeutig/disjunkt), `stop_milestone`, `approval`, `body` (höchstens 8 KiB). Operations-Enum: `read, edit, test, commit, push, report, network, external-write`; unerwähnt heißt verboten. `tests-green` verlangt `test`, sonst verlangt das Stop-Ziel seine gleichnamige erlaubte Operation.
5. Der aktuelle Prompt zeigt Task, beide Listen, Stop, Approval und Vorrang des engen Pakets gegenüber breiteren AGENTS-/Skill-/Phasenanweisungen. Er untersagt Umweg/anderen Transport nach Denial und verlangt `blocked`, falls Stop unerreichbar ist. Generische Folgetask-/Commit-/Push-/`pushed`-Anweisungen entfallen nur im Paketmodus. Das ist eine LLM-Anweisung, keine deterministische Operationssperre.
6. `automatic` ist für **jedes** sonst gültige Execute-Paket erlaubt. `never` behält `--sandbox workspace-write` und keine Anfrage-Route; ein notwendiger Randkontakt führt zu Task-`blocked` mit `approval-route-missing: <Aktion>`, ohne stillen Formwechsel. Fehlendes/unbekanntes Approval sowie Approval in Whole-Phase oder Review verweigern vor Spawn. Beide Formen haben denselben Sandboxrand; Review bleibt read-only mit bisherigem Schema/Output und unabhängiger Attestation.
7. Queue hält Modus, Pfad, Paket-/Source-Head, Digest, Task-ID, Klasse, Approval, Issue, Branch, Tier und Harness; `drain` prüft erneut. Identitätskollision ist Konflikt. `chain` schreibt `parent_harness` aus dem **Plan-Record** in den Review-Eintrag und Review-Record; ein Codex-Plan bleibt auch unter Claude-Review Codex-geplant. Nach dessen Planreview wird kein Execute automatisch gequeued: neuer Steward-Paketcommit und explizite Codex-Queue. Legacy-Record ohne `parent_harness` gilt als Claude; alte Claude-Queues bleiben lesbar.
8. `build_argv` ist der einzige argv-Bauort. Nur ein validiertes Execute-Paket mit `automatic` erhält `--approve-for-me` **anstelle** von `--sandbox workspace-write`; Execute erhält `--json` und `-c model_reasoning_effort=<effort>`. `_dispatch_codex.executable` prüft die exakte Form als zweite Schranke. Keine weiteren Flags, kein Provider-Override, kein Profil. Katalogprobe bleibt vor Spawn. Eine Ablehnung erzeugt genau einen Execute-Versuch ohne Supervisor-Retry/Transportwechsel; die echte Agentenreaktion innen ist damit nicht bewiesen.
9. Execute-stdout wird als JSONL nur auf feste Typ-/Zählfelder projiziert; stderr nur als Zeit-/Byte-Aktivität, nie Freitext. Grenzen: 64 KiB pro Zeile, 100 Ring-Ereignisse, 2 KiB je `list`/`log`, begrenzter Tail und Zeitbudget. Fehlendes, defektes oder unbekanntes JSON wird `partial`/`unavailable`; stderr-only bleibt sichtbar. Nur verifizierter Supervisor/Terminal-Receipt bestimmt Prozessstatus, unabhängiger Handoff das Reviewurteil. Eine `blocked`-Schlussnachricht bei Exit 0 bleibt als Taskbefund sichtbar und wird nie zu Task-/Review-PASS erklärt.

## Verifizierte Upstream-Anker und spätere Aufgaben

Stand dieses Plans ist der Base-Commit oben. Die Signaturen wurden am tatsächlichen Upstream gelesen; Zeilen können nach der PLAN-Review wandern. Tasks sind **sequenziell** wegen gemeinsamem Dispatcher/Queue/Supervisor. Vor jedem Code-Task zuerst ein am alten Pfad roter Akzeptanztest, danach derselbe grün. Kein Testlauf wird durch diesen Plan behauptet.

| Task | Aktueller Owner/Signatur und Anker | Roter/Grüner Upstream-Test, Akzeptanz |
|---|---|---|
| U001 Paket/Prompt/Head | `dispatch.py:1142 prompt_for(phase, issue, tier, branch, model, …)`, `:1106 sync_worktree(root, wt, branch, phase)`, `:1736 start(root, *, issue, phase, tier, branch, title, dry_run, …)`; `_dispatch_codex.py:298 launch(parent, argv, cwd, env, metadata, *, deadline_s)` mintet heute UUID selbst | Neue `tests/test_dispatch_codex_packets.py::test_packet_commit_parent_and_current_prompt` und `::test_stale_or_changed_packet_refuses_before_spawn`: Branch-Blob vor Sync, Parent/ein Pfad, Worktree-HEAD/Blob/Bytes nach Sync, Prompt-Vorrang, eine Invocation; negative Self-HEAD, Metadatencommit, Symlink/Drift, explizite Whole-Phase. |
| U002 Zelle/Queue/Chain | `dispatch.py:360 cell_for(policy, tier, phase, cls=None)` hat Klassen-Precedence; `:1736 start` ruft derzeit ohne Klasse; `:2369 _valid_entry(e)`, `:2425 _same_line(a,b)`, `:2430 queue_add(root, *, issue, phase, tier, branch, plan_review=False, harness=None)`, `:2446 drain(root)`, `:2820 _chain(root, *, dry_run=False)`, `:2938 main(argv)` | `::test_plan_review_then_explicit_codex_queue_keeps_cell` und `::test_packet_commit_keeps_plan_review_clearance`: Codex-Plan→Claude-Review→kein Auto-Execute→neuer Paketcommit→Queue/Drain; Klasse/Modell/Effort/Tier identisch; fehlende Werte verweigern; Legacy-Verhalten. Clearance über `dispatch.py:2666 uncleared_plans(root, head, branch='')`, `check_review.py:89 record_kind(rel)`, `plan_drift.py:249 check_execute(…)`. |
| U003 Approval/argv | `dispatch.py:618 build_argv(policy, model, prompt, branch='', issue=None, phase=None, effort=None, command=None)`; `_dispatch_codex.py:53 executable(argv, model, phase, effort, preview=False)`, `:79 probe(…)`; gegenwärtige Allowlist nur Sandbox-Form | `::test_approval_scope_and_rejection`: zwei automatische Positivfälle (native `[read,edit,test]` mit Git/Report/Netz/extern verboten; enges Report/Netz ohne Git), `never`-Zwilling, fehlendes/unbekanntes Approval, Whole/Review-Refusal, exakte argv/Prompt-Listen. Fake-`codex` auf temporärem PATH antwortet Katalog und lehnt Execute ab: ein `started.json` `attempt=1`, `terminal.json` failed, Rohlogs, kein zweiter Spawn. |
| U004 Fortschritt/Taskstatus | `_dispatch_codex.py:376 supervise(evidence)` schreibt getrennte `stdout.log`/`stderr.log` und `terminal.json`; `dispatch.py:2052 list_sessions(root)`, `:2105 show_log(root, branch, lines)` | `::test_stderr_only_progress_is_bounded_and_not_a_verdict`: gültiges/kaputtes/überlanges JSONL, stderr-only, Redaction, Limits, Prozess0 plus Task-`blocked` sichtbar ohne PASS-Verwechslung; Review-Schema/-o unverändert. |
| U005 Integration | `tests/test_dispatch_codex.py` enthält Fake-CLI, Katalog-, Supervisor- und Handoff-Fixtures; `tests/test_dispatch.py` Queue/Chain/Prompt/Planreview; `tests/test_model_policy_local.py` Overlay-Zellen; `tests/conftest.py` rendert ein gitfreies Snapshot des Template-Arbeitsstands | `::test_packet_failure_matrix_preserves_claude_and_review`: mindestens ein echter Dispatcher→Supervisor→Kindprozess-Weg im temporären Git-Repo; Scope-/Modell-/Effort-/Approval-/Digest-/Invocation-Negativzwillinge, Claude-Routing, Guard-/Review-Regressions. Danach betroffene bestehenden Testgruppen und gerenderte Varianten. |

**Upstream-Kommandos nach freier Planreview/Refute, nicht in dieser PLAN-Phase:** `uv run pytest tests/test_dispatch_codex_packets.py -q` (neu, zuerst rot, dann grün), `uv run pytest tests/test_dispatch_codex.py tests/test_dispatch.py tests/test_model_policy_local.py -q`, `uv run ruff check .`, `uv run pytest -n 4 --dist loadfile`. `tests/conftest.py`-Renderpfad ist für Minimal/Standardset zu nutzen; `tests/test_adapters.py`, `tests/test_command_adapters.py`, `tests/test_ci_adapters.py`, `tests/test_brownfield.py`, `tests/test_template_verify.py` und der portable macOS-/Windows-Smoke sind die betroffenen Generik-Belege. Die genauen Varianten/Ergebnisse gehören in die spätere Code-Review, nicht als hier bereits bestanden.

## Migration, Kompatibilität, Rollback

Vorhandene Claude-Starts, Claude-Queues und immutable historische Records behalten ihre Lesbarkeit und ihr Routing. Codex-Execute verlangt künftig explizit Paket+Klasse oder Whole-Phase; alte Codex-Execute-Queuezeilen ohne Modus verweigern und müssen vom Steward nach Prüfung neu gequeued werden. Vollphasenmodus transportiert keine Approval-Opt-in und nutzt `standard`/workspace-write; Review bleibt read-only. Die generische Codex-Policy behält Modell-IDs, ergänzt nur explizite Effort-Zellen und beide Command-Templates. Projekt-Overlays mit alten String-Zellen ersetzen nach `cell_for` weiterhin ganze Zellen; ohne eigenen Effort werden sie **benannt verweigert**, bis das Projekt im lokalen Overlay Modell+Effort ergänzt. Keine implizite Übernahme eines Tier-Efforts, keine Modellsubstitution. Die releaseabhängigen Schritte sind als Migrationshinweis und geänderter Template-Doc-Abschnitt aufzunehmen; ob ein reines Update oder ein eigenes Migrations-Release nötig ist, entscheidet der Owner anhand des realen späteren Diffs nach `MAINTAINING.md`/`releases.md`.

Rollback vor Release: Branch verwerfen oder eigene Code-Commits zurücknehmen, ohne Gate-/Policy-Ausnahme. Nach Release: auf vorherigen gepinnten Template-Stand zurückgehen, Codex-Queue vor erneuter Ausführung explizit bereinigen und die alten CLI-/Policy-Formen wiederherstellen; kein automatisches Uminterpretieren der neuen Paket-Records. Projekt-Sync erfolgt erst nach Owner-Release über gepinnten normalen `template_update.py`-Pfad und getrennten lokalen Modellwerten. Dieser Upstream-Plan behauptet keine Projekt-Gates, keine Native-Probe und keinen Sync.

## Unabhängige Durchsetzung und Abschlussfolge

1. **Vor Code:** Upstream-Plan-Review in frischer unabhängiger Sitzung auf diesem exakten Planstand; Tier-3-Refute vor Code-Runde 1. Der aktuelle Projekt-R4-Review ersetzt beides nicht. Bei widersprechendem Source-Anker oder Contract: `DECISION NEEDED` hier erfassen und betroffenen Teil stoppen, ohne schwächere Semantik zu erfinden.
2. **Codephase erst nach Stufe 1:** U001–U005 mit Red/Green-Belegen in Upstream-`tests/`; keine Selbstattestation. Der Fake-CLI-Test begrenzt seinen Anspruch auf Supervisor-Verhalten, enthält aber eine Prompt-Assertion für STOP nach Denial. Prozessstatus, Taskbefund und Reviewurteil werden separat geprüft. Keine neue Security-Framework- oder Gate-Implementierung.
3. **Unabhängige Codeprüfung:** frische, Tier-3-taugliche Review plus Refute-Belege und attestierter exakter Code-Head. `uv run ruff check .` und `uv run pytest -n 4 --dist loadfile` tatsächlich ausführen. Generik nach `MAINTAINING.md`: Minimalrender ohne Module, Standardset, alle Harnesses, CI an/aus, Brownfield, Update und portable macOS-/Windows-Smoke bei Laufzeitcode. Positives Einzelprojekt-Ergebnis genügt nicht.
4. **Owner-Release und downstream:** Version/CHANGELOG/NEWS/Migrationsklassifikation nur in separater autorisierter Release-Arbeit. Owner gibt Release frei; danach gepinnter normaler Template-Sync im Projekt und dessen eigene Prüfungen. Keine Freigabe, kein Release und kein Sync durch diesen PLAN-Worker.


## Anhang: eingefrorener Worker-Packet-v1-Vertrag

Die folgende Vertragskopie ist lokal im Upstream-Plan abgelegt; spätere Ausführung benötigt keinen privaten Projektpfad. Abweichungen vom obigen Port sind vor Code als Entscheidung zu klären.

# Worker packet v1 — Entwicklungs-Dispatcher

Owner: `scripts/process/dispatch.py` wählt Modus, liest und validiert den
Vertrag; `scripts/process/_dispatch_codex.py` beaufsichtigt genau diese
Invocation und schreibt deren Belege. Kein Produkt-API-Vertrag.

## Erzeugung, Modus und Quelle

Nach dem Planreview wählt der Steward einen offenen Task aus `tasks.md`,
schreibt eine reguläre UTF-8-JSON-Datei unter
`specs/<feature>/packets/<task_id>.json` und committet **nur diese Datei** in
einem neuen Single-Parent-Commit. `source_head` ist der volle SHA vor diesem
Commit; der danach entstehende `packet_head` steht absichtlich nicht in der
Datei. Der Dispatcher verlangt `HEAD == packet_head`, `HEAD^ == source_head`
und einen Commit-Diff mit genau dem Paketpfad. Bloße Vorfahrenschaft, ein
späterer Metadatencommit oder Rebase autorisieren das Paket nicht. Für den
nächsten Task wird auf dessen aktuellem Branch-Head ein neues Paket committet.

Codex-`execute` verlangt genau `--packet <repo-relativer Pfad> --class
<task class>` oder `--whole-phase`. Ein Paketstart liest vor jeder Mutation im
Main-Checkout `packet_head = git rev-parse <branch>^{commit}` und den Blob
`git show <packet_head>:<packet_path>`, nie `HEAD:`, denn das HEAD des
Main-Checkouts ist nicht der Branch. Der offene Task und seine Klasse kommen
aus `<packet_head>:specs/<feature>/tasks.md` (gegenüber `source_head`
unverändert). Ein vor Sync noch fehlender Worktree ist kein Lesefehler. Nach
`sync_worktree` und unmittelbar vor `launch` gilt im Ziel-Worktree
`git rev-parse HEAD == packet_head`; `HEAD:<packet_path>` hat dieselben
Blobbytes und die Worktree-Datei dieselben Bytes (`packet_sha256`), ohne
Dirty-Status. Auch ein Fast-forward nur um Metadaten
verweigert. Ein Paket ist maximal 16 KiB, ohne Symlink/Pfadausbruch und dirty
Worktree-Datei. `--whole-phase` nutzt ausdrücklich den bisherigen Prompt,
`standard`-Klasse und `--sandbox workspace-write`; andere Klasse oder
Approval-Opt-in sind verboten. Claude-Starts bleiben kompatibel. Ein
unmarkierter oder alter Codex-Execute-Eintrag bedeutet nie Vollphase.

| Feld | Form | Bindung |
|---|---|---|
| `version` | Integer `1` | unbekannte Version verweigert |
| `issue`, `branch`, `phase`, `tier` | Zahl, Name, `execute`, 0–3 | Startargumente/Record |
| `task_id`, `class` | `T[0-9]{3,}`, Policy-Klasse | offener `tasks.md`-Marker; `--class` gleich |
| `source_head` | voller Git-SHA | Parent des ausschließlich das Paket ändernden `packet_head` |
| `allowed_operations` | nichtleere Liste eindeutiger Enum-Werte | positive Befugnisgrenze im Prompt |
| `forbidden_operations` | Liste eindeutiger Enum-Werte | disjunkt zu `allowed_operations` |
| `stop_milestone` | Enum `tests-green`, `commit`, `push`, `report` | muss zur erlaubten Operation passen |
| `approval` | Enum `never`, `automatic` | Pflichtfeld; kein Policy-Default |
| `body` | UTF-8-Tasktext, maximal 8 KiB | gegen Task in `tasks.md` geprüft |

Operationen sind ausschließlich `read`, `edit`, `test`, `commit`, `push`,
`report`, `network` und `external-write`; ein nicht aufgeführter Wert ist
verboten. `stop_milestone` `tests-green` verlangt `test`, die anderen Werte
die gleichnamige erlaubte Operation. Drei Schichten bleiben getrennt:

1. **Auftrag:** Das Paket begrenzt im sichtbaren Prompt, was der Worker
   versuchen und eskaliert anfragen darf.
2. **Sandbox:** `workspace-write` ist bei `automatic` und `never` dieselbe
   Grenze. `automatic` erweitert weder writable roots noch Netzwerk noch
   geschützte Pfade. Es gibt keine globale Konfiguration, keine
   Rules-Änderung, kein Profil und keinen Bypass.
3. **Freigabe je Aktion:** Mit `--approve-for-me` entscheidet ein separater
   Auto-Review-Agent jede einzelne eskalierte Anfrage anhand des sichtbaren
   Transkripts (Nutzer- und Assistentnachrichten, Toolaufrufe, die exakte
   Anfrage; kein verborgenes Reasoning).

`approval` ist die explizite Wahl des Prüfers je Paket, keine
Operationsfreigabe. `automatic` ist für jedes sonst gültige Execute-Paket
zulässig. Dafür muss weder jede noch eine bestimmte Operation erlaubt sein.
Bis zu einer berechtigten Anfrage entsteht weder Kosten- noch
Rechtewirkung. Operationsnamen sagen den Sandboxrand nicht voraus, denn auch
`read`, `edit` und `test` können ihn brauchen. Beleg: native
`xcodebuild`-/Xcode-MCP-Tests eines reinen Testpakets scheiterten unter
`never` an der fehlenden Approval und an der Simulator-Sandbox. Deshalb
leitet keine Regel `automatic` oder `never` aus `allowed_operations` ab,
und es gibt keine Meldung „Approval unnötig“.

Vor Spawn verweigert die bestehende Paketvalidierung mit Exit 3 in diesen
Fällen:

- `approval` fehlt oder hat einen unbekannten Wert;
- `automatic` in Whole-Phase oder Review;
- die bestehenden Prüfungen schlagen fehl (Enum der Operationen,
  `allowed`/`forbidden` disjunkt).

`never` heißt: keine Anfrage-Route. Braucht eine Aktion dann den
Sandboxrand, endet der Worker `blocked` mit
`approval-route-missing: <exakte Aktion>`. Ist dieser Bedarf statisch
bekannt, nennt der Steward die fehlende Route vorab. Es gibt keinen stillen
Wechsel auf `automatic` und keinen anderen Transport. Ein explizites
`never` ist Operatorwahl, kein Beleg, dass ein nativer Lauf ohne Eskalation
gelingt.

Der Paketprompt ist eine sichtbare Nutzernachricht und zitiert Task, beide
Listen, Stop und Approval-Wahl. Eskalierte Anfragen sind nur für erlaubte
Operationen und nur mit Taskbezug zulässig. Der Auto-Reviewer kann auch
passende Anfragen ablehnen. Eine Ablehnung beendet diese Aktion; der Worker
verfolgt dasselbe Ergebnis nicht über Umweg, indirekte Ausführung oder
anderen Transport. Ist der Stop dann unerreichbar, endet der Worker mit
einer `blocked`-Schlussnachricht. Das ist ein Prüfer-Tausch, keine
Pauschalfreigabe, keine Zusage einer Genehmigung und keine deterministische
Sicherheitsgarantie. Eine CLI-Schranke je Operation gibt es nicht und wird
nicht behauptet. Verbotene und ungenannte Operationen und die eine
Stop-Bedingung stehen im aktuellen Paketprompt. AGENTS.md, Skills und
`/execute` liefern Verfahren und Sicherheitsregeln, aber deren breitere
Phasenanweisung autorisiert keine hier fehlende Operation. Bei Konflikt
meldet der Worker `blocked`. Der generische Satz zu Folgetasks, Commit,
Push und `pushed` wird im Paketmodus nicht nachgehängt.

Der Dispatcher erzeugt **eine** UUID `invocation` vor dem Start und
`packet_sha256` über exakte rohe Git-Blobbytes. Prompt, Launch-Record,
`launch.json`, `started.json` und `terminal.json` referenzieren dieselbe
Invocation, `packet_head` und denselben Digest; Modus, Klasse, Modell,
Effort und Approval bleiben in den Belegen. `launch` übernimmt die UUID,
statt eine zweite zu erzeugen. Vollphase hat `null`-Paketfelder. Ausgabe des
Pakettexts im Status ist verboten. Doppelte JSON-Schlüssel, unbekannte oder
fehlende Felder, inkonsistente Klasse/Phase, geänderte Bytes/Head, ungültiges
UTF-8, Symlink und Größenüberschreitung verweigern benannt mit Exit 3 vor
Kindprozess, ohne Fallback. Dasselbe gilt für Read-/Sync-/Policyfehler.

`queue add` validiert die Quelle vor dem Speichern und hält `harness=codex`,
Issue, Branch, Tier, Modus, `packet_path`, `packet_head`, `source_head`,
`packet_sha256`, Task-ID, Klasse und Approval. `drain` validiert alles neu;
ein verweigerter Eintrag bleibt zur expliziten Korrektur. Ein gleicher
Issue-/Phasen-Key mit anderer Identität ist Konflikt, kein stilles No-op.
Alte Claude-Zeilen und Records bleiben lesbar; alte Codex-Execute-Zeilen
ohne Modus verweigern und werden explizit neu gequeued.

`chain` darf nach `planned` die normale Tier-3-Planprüfung einreihen. Nach
Planreview-Pass reiht es für **Codex-geplante** Arbeit kein Execute ein.
„Codex-geplant“ ist ein Record-Feld, kein Rückschluss aus dem Reviewer.
Queued `chain` die Planprüfung nach einem `planned`-Report, schreibt es
`parent_harness` = `harness` des Plan-Records in den Eintrag (`"codex"`;
fehlt das Feld, `"claude"`), über `queue_add(..., parent_harness: str | None =
None)`. `start` übernimmt den Wert unverändert in den Review-Record. Nach
dem Pass liest `chain` nur dieses Feld. Ein Codex-Plan unter
Claude-Planreview bleibt also `parent_harness="codex"`. Ein Altrecord ohne
das Feld gilt als `claude` (bisheriges Verhalten). Für `codex` gilt:
erst der Steward committet ein Paket auf dem aktuellen Review-Head und ruft
`queue add --harness codex --phase execute --packet … --class …` (oder
ausdrücklich `--whole-phase`) auf. `drain` startet dann dieselbe Codex-Zelle.
Auch direktes `start` eines Pakets verweigert
`packet plan-review-pending`, solange `uncleared_plans(root, packet_head,
branch)` den Plan des Issues nennt. Die Gates belegt der normale Pre-Push des
Paketcommits; es gibt keinen neuen Dispatcher-Gate. Dass der Paketcommit unter
`specs/<feature>/packets/` die Clearance nicht entwertet, beweist
`test_packet_commit_keeps_plan_review_clearance`. Wird dieser Test rot, ist
das ein benannter Blocker für den Upstream-Plan, kein Gate-Fix in #2675. Vor Reviewende
gequeuete Pakete verweigern; deren Head wird durch die Attestation stale.
Das ist ein benannter Stopp mit Fortsetzung. Claude-Chaining bleibt; ein
Codex-Review überträgt keine Execute-Klasse oder Approval. Aus einem
Codex-Record darf `chain` keinen harnesslosen Execute-Eintrag erzeugen.

## Modell, Approval und Fortschritt

Die wirksame Codex-Zelle enthält Modell **und** Effort. `classes` gewinnt vor
Tier/Default; eine fehlende Klasse für den gewählten Task, ein fehlender Effort
in der wirksamen Zelle, ein nicht transportierbarer Wert oder ein nicht im
CLI-Katalog vorhandenes Modell verweigern vor Spawn. Der Tier-3-Wert bleibt
im Record; Review nutzt seine Tier-Zelle ohne Execute-Klasse. Die lokale
Kenni-Policy wählt `mechanical: gpt-6-luna/low` und
`design: gpt-6-sol/medium`; ohne vorhandenen Katalogeintrag kein Ersatz.
Auch `phases.review.command` trägt `{effort}`. Die stehende No-Astra-Vorgabe
ist eine **Operator-Route**, kein neuer Dispatcher-Guard: der Steward startet
keine Astra-Zelle und nutzt die unabhängige Claude-Planreview-Route. Tier 3
bleibt bestehen; kein Tier- oder Modell-Fallback.

`build_argv` in `dispatch.py` ist die **einzige** argv-Baustelle. Die
Policy-Vorlage bleibt im normalen `--sandbox workspace-write`-Modus und
enthält weder `--approve-for-me` noch `--json` als globalen Opt-in. Nur für
ein vollständig validiertes Execute-Paket mit `approval=automatic` ersetzt
`build_argv` das Sandbox-Paar durch `--approve-for-me`; es ergänzt für
Execute `--json` und `-c model_reasoning_effort=<effort>`.
`_dispatch_codex.executable(argv, model, phase, effort, *, mode, approval,
allowed_operations, preview)` validiert die exakte argv-Form samt
Autorisierung, als zweite Prüfung nach der Paketvalidierung (`ValueError`).
Approval ohne Packet-Modus oder mit fehlendem bzw. unbekanntem Wert,
gleichzeitiges `--approve-for-me`/`--sandbox`, Bypass-Flags und Approval im
read-only Review verweigern. Ein tatsächlicher Ablehnungsbeleg bleibt im
Rohlog; die Aktion stoppt ohne zweiten Transport oder Retry. Die
unabhängige Reviewentscheidung bleibt separat.

`--json` ist für Execute zulässig; Review behält seine bestehende Schema-/
`-o`-Ausgabe und erhält keinen neuen Progress-Modus, bis ihre Verträglichkeit
mit einem echten CLI-Beleg gezeigt ist. Der Supervisor erfasst JSONL-stdout
und stderr separat. Für bekannte JSONL-Events werden nur feste Typ-/Zähl-
felder projiziert; bei reinem stderr-Text nur ein festes Signal `stderr
activity` mit Zeit/Bytezahl, **niemals** Freitext. Pro Zeile maximal 64 KiB,
im Ring maximal 100 reduzierte Ereignisse, pro `list`/`log` höchstens 2 KiB;
Datei-Tail und Arbeit sind ebenfalls begrenzt. Fehlendes/kaputtes/unbekanntes
JSON oder fehlendes `--json` ergibt `partial`/`unavailable`, nicht Stille;
`stderr activity` bleibt sichtbar. Nur verifizierter Supervisor und
`terminal.json` liefern `completed`/`failed`/`interrupted`; nur der unabhängige
Handoff liefert ein Review-Urteil. Progress enthält weder Prompt, Secrets,
Tool-Argumente noch rohe Tool- oder Modelltexte.
