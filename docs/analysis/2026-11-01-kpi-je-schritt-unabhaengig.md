# KPI je Prozessschritt — unabhängige Analyse

Stand: 2026-11-01, Template-Stand v2.80.1 (`213302b`). Nur Analyse und Vorschlag, kein Code geändert.

Auftrag (Owner, über die Sitzung „dev-process optimierung“): den Prozess so messbar machen, dass ein anderer Agent auf Basis der Daten auf **Fehlerfreiheit** und **Geschwindigkeit** optimieren kann. Je Schritt eine Qualitäts-KPI (Q), eine Geschwindigkeits-KPI (S) und eine Gegen-KPI (G), die eine einseitige Optimierung sichtbar macht.

Erarbeitet ohne Kenntnis von Draft-PR #356; der Vergleich steht am Ende (Abschnitt 6) und wurde erst geschrieben, als die Abschnitte 1–5 fertig waren.

## 0. Grenzen dieser Analyse

- **Kenni war nicht lesbar.** `add_repo` für `Crashman1983/kenni` wurde in dieser Sitzung abgelehnt, und die GitHub-Werkzeuge sind auf `dev-process` beschränkt. Die Spalte „Kenni“ stützt sich deshalb auf die Kenni-Zahlen, die frühere Pläne in `docs/analysis/` dokumentieren (Fundstellen unten). Alles andere ist `[assumption]`. Ein Agent mit Kenni-Zugriff kann die Spalte mit den Prüfbefehlen in Abschnitt 5 in unter einer Stunde nachziehen.
- **Abkürzungen.** `PK` = `template/scripts/process/{% if modules.telemetry %}process_kpis.py{% endif %}`, `TM` = `template/docs/process/{% if modules.telemetry %}modules{% endif %}/telemetry.md`, `SP` = `template/scripts/process/`. Zeilennummern beziehen sich auf `213302b`.
- **Status im Code:** `measured` (direkt gemessen, Cockpit gibt es aus), `estimated` (berechnet, mit bekannter Unschärfe), `proxy` (misst etwas Verwandtes), `missing` (kein Code liest oder schreibt es). Steht `data-only` dabei, liegen die Rohdaten vor, aber das Cockpit wertet sie nicht aus.
- **Wo die Daten liegen.** `Git` heißt, die Daten sind versioniert und auf jedem Klon lesbar: Commits, Pläne, Journal-`REVIEW`-Zeilen, `.process-work/reviews/*.md`, `gate-triage.jsonl`. `Host` heißt, sie liegen nur im Git-Common-Dir des Rechners, auf dem gearbeitet wurde, und nie im Repository (Belege in Abschnitt 1). `gh` heißt GitHub-Issues über die `gh`-CLI.

## 1. Befund vorab: zwei Klassen von Spuren

Das Cockpit hat zwei Arten von Quellen, und daran hängt die Antwort auf „liegt in Kenni vor?“.

| Quelle | Schreiber | Ort | auf Klon/CI lesbar |
|---|---|---|---|
| Worker-Reports (`planned`, `pushed`, `review-pass`, `blocked`, `failed`, `done`; optional `usage`) | `SP/report.py:44-47, 133-154` | `<common-dir>/process-tower/reports.jsonl` (`report.py:12`) | nur über `--sync`-Refs (`report.py:16-21`) |
| Dispatch-Phasenstarts | `SP/dispatch.py` (Log-Dateiname) | `<common-dir>/process-dispatch/*.log`, gelesen `PK:1645-1656` | nein |
| Train-Läufe (Phasenzeiten, `result`, `aboard`, `branches`, `deployed`, `ended`) | `SP/train.py:1338-1356` | `<common-dir>/process-train/phases.jsonl` (`train.py:67`) | nein |
| Gate-Ereignisse (gate, mode, outcome, rc, duration_s) | `SP/gate_runner.py.jinja:383`, `SP/plan_drift.py` | `<common-dir>/process-gate-events.jsonl` (`SP/gate_events.py:3, 15`) | nein (TM: „a fresh CI checkout has no log“) |
| Merge-Ereignisse, Produktzeilen, `Regression-of:` | git | Integrationsbranch (`PK:1914, 1954, 1676`) | ja |
| `REVIEW`-/`DECISION`-Zeilen, Pläne mit `tier:` | `SP/attest.py`, Pläne | Journal und Pläne | ja |
| Review-Berichte mit `FINDING`-Zeilen | Review-Sitzungen | `.process-work/reviews/*.md` | ja, solange `tidy.py --apply` sie nicht gelöscht hat (`SP/tidy.py:454-455`) |
| Gate-Triage | Mensch/Steward | `.process-work/gate-triage.jsonl` (TM, „Gate triage“) | ja |

Daraus folgen drei Dinge:

1. **Jede Geschwindigkeits-KPI je Phase hängt an Host-Daten**, also Arbeits- und Wartezeit, Tokens, Gate-Kosten, Train und Deploy. Ein Klon und der monatliche CI-Lauf (`TM:92`, `process-kpis.yml`) sehen davon nichts. Die Qualitäts-KPIs (Runden, Blocker, Durchrutscher) kommen dagegen seit v2.80 aus Git (#341, `TM`, „Merged works come from git“). Das ist eine **Lücke im Template**, nicht in Kenni: nur die Reports haben einen Sync-Weg.
2. Vor v2.80 zählte das Cockpit auf jedem Klon `works 0`. Die Kenni-Analyse zu v2.80 lief deshalb von Hand (`docs/analysis/2026-10-28-v2.80.md:19`).
3. `tidy.py --apply` löscht ältere Berichte. `baseline` muss vorher laufen (TM, `baseline`). Damit ist die Review-Historie nur verlustbehaftet in Git.

Belegte Kenni-Bestände (aus früheren Plänen):

- 8 Wochen: 9.111 Commits, 281 Train-Merges, 1.879 `REVIEW`-Zeilen, Median-Durchlaufzeit 5,5 h (`docs/analysis/2026-10-28-v2.80.md:11-17`).
- 571 Review-Berichte und 2.331 `FINDING`-Zeilen. Nur 24 % trugen einen Ort, nur 36 von 233 Code-Berichten ein `head=` (`docs/analysis/2026-10-24-v2.78.md:13-21`). `at=` ist erst seit v2.78 Pflicht.
- 510 Issues mit 808 Runden zwischen 1.9. und 21.10. (`docs/analysis/2026-10-21-v2.77.md:13`).
- Ein Kalibrierungs-Audit fand 6 Major-Fehler in 6 Tier-2-Arbeiten, die in Runde 1 bestanden hatten (`docs/analysis/2026-10-14-review-evidence.md:7`).
- Suite-Timeouts, Push-Timeouts und ein flakiger Test (Kenni #2711, #2717), zitiert in Issue #317.

Ob Kennis Steward-Host die Host-Dateien vollständig hat, ist `[assumption]`. Plausibel ist es für die Zeiträume, in denen Dispatch und Train dort liefen.

## 2. KPIs je Schritt

Spalten: **Def.** = Definition · **Einh.** = Einheit · **Ri.** = Richtung (↓ kleiner ist besser, ↑ größer ist besser, → nur Trend lesen) · **Quelle** · **Status** · **Kenni** (`ja`, mit Fundort, wenn belegt; `[assumption]` sonst; `nein`, wenn nichts erzeugt wird).

Grundsatz aus TM („honest ceiling“): nur im eigenen Projekt vergleichen, Trends statt Absolutwerte, Ereignisse statt Quoten. Keine KPI ist ein Ziel. Jede KPI unten nennt deshalb die Entscheidung, für die sie gebraucht wird. Eine KPI ohne Entscheidung habe ich weggelassen.

### 2.1 Issue / Eingang

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Verworfene gestartete Arbeit** | Anteil der Issues mit mindestens einem Dispatch-Phasenstart, die ohne Merge-Ereignis als `not planned`/`duplicate` geschlossen wurden | % (n zuerst) | ↓ | Phasenstarts `PK:1645`, Merge `PK:1954`, Schließgrund über `gh` (`PK:2737`, Muster aus `outcomes`, das ihn bei Bugs schon liest, TM `outcomes`) | missing (data-only) | `[assumption]` Host + gh |
| S | **Wartezeit bis Start** | Issue `createdAt` → erster Dispatch-Phasenstart, sonst früheste Autorzeit | h, Median/P90 | ↓ | `gh` + `PK:1645` / `PK:1954` | missing (data-only) | gh ja `[assumption]`; Start aus Git `estimated` |
| G | **Arbeit ohne Issue** | Merges, die kein Issue beanspruchen, und Arbeiten ohne Plan oder `REVIEW`-Zeile | n je Fenster | ↓ | `population`-Zeile (`PK:1092-1124`) | measured | ja (Git) |

Entscheidung: Wartet Arbeit vor dem Start (Steward-Kapazität, Priorisierung) oder danach? G verhindert, dass die Eingangszeit dadurch sinkt, dass Arbeit am Issue vorbei läuft.

### 2.2 Tier-Einstufung

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Durchrutscher je Tier** | gemergte Arbeiten mit späterem `Regression-of: #N` im geschlossenen Folgefenster, je Tier | n und % (`thin` < ~20) | ↓ | `baseline` je Tier (`PK:1127-1210`, `_work_tier PK:1062`, `_regressions PK:1676`) | measured (Ereignis), Quote proxy | Git ja. Nutzung des Trailers in Kenni `[assumption]` |
| S | **Kosten je Tier** | Median der Code-Runden und Tokens je gemergter Arbeit, je Tier | Runden, Tokens | ↓ | `baseline`/`works` je Tier (`PK:2412`) | Runden measured; Tokens nur Host | Runden ja (Git); Tokens `[assumption]` Host |
| G | **Tier-Unterschätzung** | Arbeiten, deren höchstes `REVIEW tier=` über dem `tier:` des Plans liegt | n je Fenster | ↓ | `_work_tier` liest beides schon (`PK:1062-1073`); REVIEW-Grammatik `template/docs/process/journal-state-plans.md:244` | missing (data-only) | ja (Git) |

Entscheidung: Lohnt Tier 3 (Kosten hoch und Durchrutscher nicht niedriger, `risk-tiers.md`: „that cost, not escaped defects, became the bottleneck“)? G zeigt, ob man die Kosten durch zu niedrige Einstufung senkt.

### 2.3 Spec / Brainstorm / Klärung

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Späte Fragen** | `DECISION NEEDED`, die nach dem Plan-Review-Pass (`REVIEW work=<id>-plan`) in den Plan kommen, je Arbeit | n je Arbeit | ↓ | git-Verlauf des Plans; Grammatik `SP/check_review.py:380` | missing (data-only) | ja (Git) |
| S | **Klärdauer** | Start der Brainstorm-Phase → Start der Plan-Phase (Arbeit und Warten getrennt) | h | ↓ | Phasenstarts (`PK:1616` kennt `brainstorm`) und Reports | missing: `flow` summiert nur `work_s`/`wait_s` je Issue (`PK:2185-2187`) | `[assumption]` Host |
| G | **Owner-Last** | owner-`DECISION`-Zeilen je Arbeit (proxy, `PK:1696`) und Owner-Wartezeit je beantworteter Frage (#319) | n; h | → | `flow`/`losses` | Zeilen proxy measured; Wartezeit missing (#319) | ja (Git) |

Entscheidung: Lohnt eine gründlichere Klärungsrunde (workflow.md, Brainstorm: „one well-prepared round early is cheaper …“)? Q und S gegeneinander lesen. G zeigt, ob die Klärung auf den Owner abgewälzt wird.

### 2.4 Plan

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Plan hält nicht** | `REPLAN … increment\|rebuild` je Arbeit, `rebuild` getrennt | n je Arbeit | ↓ | `REPLAN_LINE` `SP/check_review.py:417`; Pflicht laut `workflow.md.jinja:47` | missing (data-only, das Cockpit liest REPLAN nicht) | `[assumption]` (Regel erst seit Fix-Runden-Regel) |
| S | **Planphase** | Arbeitszeit der Phase `plan` (Start → `planned`-Report) | h | ↓ | Phasenstart + Report | missing (nur Summe in `flow`) | `[assumption]` Host |
| G | **Schnittgröße** | Runden und Prozesszeilen je Produktzeile nach Größenklasse; Plan-Drift beim Execute-Start | Runden/100 Zeilen; Commits hinter | ↓ | `size` (`PK:2587`); `plan-drift` in `nodes` (optimization.md, „Plan drift“) | measured (proxy); Drift measured (Host) | Größe ja (Git, `2026-10-28-v2.80.md:14`); Drift `[assumption]` Host |

Entscheidung: Wird der Plan zu schnell und zu groß geschnitten? G zeigt Größe und Veralterung, Q das Ergebnis.

### 2.5 Plan-Review

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Ertrag des Plan-Reviews** | Code-Runden und `origin=draft`-Blocker je Arbeit **mit** gegen **ohne** Plan-Review, gleiches Tier | Runden, Blocker | ↓ (Differenz ↑) | `baseline` (`PK:1127`: „median rounds with and without a plan review“) | measured (proxy) | ja (Git); `origin=` nur, wo Berichte es tragen |
| S | **Kosten des Plan-Reviews** | Tokens und Arbeitszeit der Plan-Review-Sitzungen je Arbeit | Tokens, min | ↓ | Dispatch kennt nur `review` (`SP/dispatch.py:127`, `PK:1616`). TM: „plan rounds carry none“ | missing | nein: nicht unterscheidbar |
| G | **Überprüfte Pläne** | Anteil der Arbeiten mit ≥ 2 Plan-Review-Runden; Arbeiten mit begründetem Skip | % ; n | → | `rounds` by round, Plan getrennt (`PK:1356`); `_skips_by_kind` (`PK:1038`) | measured | ja (Git) |

Entscheidung: Lohnt das Plan-Review je Tier? Ohne S ist das nicht entscheidbar, weil der Ertrag messbar ist und die Kosten nicht.

### 2.6 Umsetzung (Execute) inkl. Fix-Runden

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Entwurfsfehler je Größe** | `origin=draft`-Blocker der Runde 1 je 100 Produktzeilen; `origin=fix`-Blocker ab Runde 2 getrennt | Blocker/100 Zeilen | ↓ | `rounds`/`baseline` (`PK:684`, `PK:738`), Produktzeilen `PK:1787` | proxy (nur, wo Berichte `origin=` tragen) | `[assumption]`: Abdeckung von `origin=` unbekannt |
| S | **Execute-Zeit und -Tokens** | Arbeitszeit der Phase `execute` plus Fix-Phasen; Tokens je Phase (`report.py --usage`) | h; Tokens | ↓ | Phasenstart, Reports (`SP/report.py:110, 265`), Transkripte (policy `transcripts`) | Tokens measured (Host); Zeit je Phase missing | `[assumption]` Host |
| G | **Fix-Disziplin** | Anteil blockierter Runden mit `ROOT-CAUSE`-Zeile, die `sites:` und rot→grün-Tests nennt; daneben der `origin=fix`-Anteil | % | ↑ / ↓ | `ROOT-CAUSE` (`SP/red_evidence.py`, `workflow.md.jinja:47`) | missing (data-only, das Cockpit liest ROOT-CAUSE nicht) | `[assumption]` |

Entscheidung: Schneller umsetzen (kleineres Modell, weniger Kontext) ist nur gut, wenn Q nicht steigt. G zeigt, ob Fixes Symptome flicken (workflow.md: „almost half of the blockers from round 2 on came from the previous round's fix“).

### 2.7 Gates (Prozess-Gates, Pre-Push, Testauswahl)

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Bestätigte Fänge je Gate** | Alleinblocks mit Triage `confirmed-defect` je Gate | n je 30 d | ↑ (je Kosten) | `nodes` (`PK:3012`), Triage (`PK:2984`) | measured; ohne Triage nur Rohblocks | Log `[assumption]` Host; `gate-triage.jsonl` `[assumption]` |
| S | **Gate- und Testzeit je Push** | Median/P90 `duration_s` je Gate; Pre-Push-Testzeit je Lauf | s | ↓ | `gate_runner.py.jinja:383`; Tests: **kein Log** (nur `gate_runner`, `plan_drift` importieren `gate_events`) | Gates measured (Host); Tests missing (#317) | Gates `[assumption]` Host; Tests nein |
| G | **Durchgelassenes** | (a) Flips (pass und fail am selben Commit), (b) `class=mechanical\|testable`-Befunde im Review, die sich in ≥ 2 Arbeiten wiederholen, (c) Auswahl-Fehlgriffe: Branch grün in der Auswahl, im Train-Bisect als Verursacher entfernt | n | ↓ | (a) `nodes`; (b) `findings` (`PK:1278`); (c) Train-Zeile hat `aboard` und `branches`, aber keine Namen der entfernten Branches (`train.py:1350-1352`) | (a)(b) measured; (c) estimated (Anzahl), Namen missing | (b) ja (Git); (a)(c) `[assumption]` Host |

Entscheidung: Gate schwächen oder streichen (Regel-Budget, optimization.md, „The rule budget“): das braucht Q mit Triage. Testauswahl enger machen: das braucht G(c), sonst wird nur Zeit verschoben.

### 2.8 Code-Review (inkl. Refute)

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Übersehen in Runde 1** | Anteil der Blocker ab Runde 2 auf Zeilen, die seit Runde 1 unverändert sind (#311) | % (mit n gemessen/ungemessen) | ↓ | `rounds` (`PK:931-1022`) | measured, nur für Befunde mit `at=` (ab v2.78) | vor v2.78 kaum (2 von 37 messbar, `2026-10-24-v2.78.md:19-20`); danach `[assumption]` |
| S | **Runden bis Pass und Review-Latenz** | Median/P90 Code-Runden bis Pass; Zeit `pushed` → `review-pass`/`blocked` je Runde | Runden; h | ↓ | Runden `PK:440`, `PK:1356`; Latenz aus Reports (`report.py:44-47`) | Runden measured; Latenz missing (data-only) | Runden ja (`2026-10-21-v2.77.md:13`); Latenz `[assumption]` Host |
| G | **Kosten je echtem Blocker / Leerläufe** | Tokens und Minuten je Review-Sitzung durch Blocker mit `action=fix`, je Reviewer-Familie und Linse; Sitzungen ohne Befund | Tokens/Blocker | ↓ | Kosten je Runde (`PK:1342`, estimated); Issue #316 | missing (#316) | `[assumption]` |

Zweite Gegen-KPI ist **Durchrutscher je Tier** (2.2/2.11). Weniger Runden sind nur gut, wenn die Durchrutscher nicht steigen. Der Kalibrierungsbefund aus Kenni (6 übersehene Majors in 6 Arbeiten mit Pass in Runde 1) ist genau dieses Muster.

Entscheidung: Linse, Reviewer-Familie und Rundenlimit wählen.

### 2.9 Merge / Train

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Ausschuss je Zug** | Anteil der Läufe mit `result=red`; Branches an Bord minus gelandete | %; n | ↓ | `phases.jsonl` (`train.py:1349-1352`) | data-only (`train-phases` zeigt nur Zeiten, `PK:1565`) | `[assumption]` Host (281 Train-Merges belegt in Git, `2026-10-28-v2.80.md:11`) |
| S | **Zugzeit und Wartezeit aufs Boarding** | Median/P90 je Phase (preflight … push); `review-pass` → `ended` des Zugs, mit dem der Branch landete | s; h | ↓ | `train-phases` (`PK:1565`); Wartezeit aus Reports + `branches` | Zugzeit measured; Wartezeit missing | `[assumption]` Host |
| G | **Batch-Effekt** | `retry`+`bisect`-Sekunden gegen `aboard` | s je Branch | ↓ | `phases.jsonl` | data-only | `[assumption]` Host |

Entscheidung: Größe und Takt des Zugs. Ein größerer Batch senkt S je Branch, bis Bisect (G) die Ersparnis frisst.

### 2.10 Deploy

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Deploy-Erfolgsquote** | Läufe mit `deployed=true` / Läufe mit Deploy (`null` = keiner) | % | ↑ | `phases.jsonl` (`train.py:1342-1352`, `1823-1826`) | data-only (nur Zeit in `flow`) | `[assumption]` Host; ob Kenni `--deploy` nutzt, `[assumption]` |
| S | **Merge → nutzbar** | Deploy-Phasendauer; Merge-Zeit → `ended` des deployenden Zugs | s; min | ↓ | `train-phases`, `flow` (`PK:1990`) | measured (Host) | `[assumption]` Host |
| G | **Wiederherstellungszeit** | Erkennung → wieder funktionsfähig, je Vorfall | h | ↓ | optimization.md:24: „not measured until the project records incidents“ | missing | nein |

Entscheidung: Schneller deployen lohnt nur, wenn Vorfälle schnell behoben werden. Ohne G wäre eine hohe Quote bei langen Ausfällen unsichtbar.

### 2.11 Nachfehler (nach Merge/Deploy)

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Durchrutscher** | gemergte Arbeiten mit `Regression-of:`-Fix im Folgefenster (30 d, `PK:1615`), nur geschlossene Fenster; Ursache und Kanal (`cause:*`, `channel:*`) | n, % | ↓ | `baseline`/`flow` (`PK:2160-2172`); `outcomes` (`PK:2812`) | measured (Ereignis); Labels estimated | Git ja; Trailer- und Label-Disziplin `[assumption]` |
| S | **Zeit bis Fix** | erster Deploy (sonst Merge) → Commit des `Regression-of`-Fixes; störende Owner-Bugs → Lieferung (`outcomes`) | h, Median/P90 | ↓ | `_regressions` (`PK:1676`) hat die Zeiten, ausgegeben wird nur die Zahl | Owner-Bugs measured; Durchrutscher-Fix missing (data-only) | ja (Git) |
| G | **Unterzählung** | `cfr`-Proxy (`fix:` ≤ 7 d nach `feat:` mit gemeinsamer Code-Datei, `PK:181`) und `clusters` (`PK:244`) gegen gemessene Durchrutscher; eine wachsende Schere heißt, dass Trailer fehlen | Verhältnis | → | `cfr`, `clusters`, `baseline` | proxy measured | ja (Git) |

Entscheidung: Ob das Gate vor dem Merge streng genug ist. G verhindert, dass die Durchrutscherquote sinkt, weil niemand den Trailer setzt.

### 2.12 Die Messung selbst

| | KPI | Def. | Einh. | Ri. | Quelle | Status | Kenni |
|---|---|---|---|---|---|---|---|
| Q | **Messabdeckung** | je Feld von `flow`/`works` (start, lead, work, tokens, escapes) der Anteil `measured`/`estimated`/`missing` über die Arbeiten im Fenster | % | ↑ measured | Qualitätsfelder liegen je Wert vor (`PK:2181-2205`), Aggregat fehlt; `population` (`PK:1092`) | estimated (je Arbeit da, keine Summe) | ja (Git-Teil) |
| S | **Aktualität** | fällige, unbeantwortete Messmeilensteine; Tage seit dem letzten Record mit Cockpit-Zahlen | n; d | ↓ | `SP/due_measurements.py` (`DUE`-Zeilen); `.process-work/optimizations/` | measured | `[assumption]` (ob `milestones.local.json` gepflegt wird) |
| G | **Messaufwand** | Prozesszeilen und -commits aus Mess- und Record-Arbeit gegen Produktzeilen | Verhältnis | ↓ | `load`/`share` (`PK:2492`, `PK:1511`) | proxy measured | ja (Git; 60–68 % reine Prozess-Commits, `2026-10-28-v2.80.md:13`) |

Entscheidung: Ob eine KPI belastbar genug zum Handeln ist (Konfidenz-Regel, TM), und ob die Messung mehr kostet als sie bringt (optimization.md: „Building, running and maintaining the optimization counts as cost too“).

## 3. Template-Lücke oder Projekt-Lücke?

| Befund | Ursache | Ort |
|---|---|---|
| Host-Daten auf Klon/CI unsichtbar (Zeit, Tokens, Gates, Train, Deploy) | Template: nur `report.py` hat `--sync` | Template |
| Plan-Review-Kosten nicht trennbar | Template: Phase `review` für beides (`dispatch.py:127`) | Template |
| Zeit je Phase und Übergabe | Template: `flow_items` summiert (`PK:2131-2156`) | Template |
| ROOT-CAUSE, REPLAN, REFUTE werden geschrieben, aber nicht gemessen | Template: kein Leser im Cockpit (`grep` in `PK` leer) | Template |
| Testlauf-Zeit, Timeouts, Flakes | Template: `test_select`/`pre_push` schreiben kein Ereignis (#317) | Template |
| Entfernte Branches im Train | Template: Feld fehlt in `phases.jsonl` | Template |
| Wiederherstellungszeit | Template hat kein Vorfallsformat; Projekt hätte keins zu pflegen | beides |
| `Regression-of:`-Trailer, `cause:*`/`channel:*`-Labels | Projektdisziplin; das Template hat Grammatik und Leser | Projekt `[assumption]` |
| Gate-Triage | Projektdisziplin (TM, „Gate triage“) | Projekt `[assumption]` |
| `FINDING`-Blocker „not read“ | Projekt ohne Modul `github-issues` oder ohne PyYAML (TM, `rounds`) | Projekt `[assumption]` |
| Review-Historie gelöscht | Projekt hat `tidy --apply` vor `baseline` laufen lassen | Projekt `[assumption]` |
| `at=`/`origin=` fehlen in alten Berichten | historisch; ab v2.78 Pflicht für Blocker/Major | Projekt (Historie) |

## 4. Die fünf wichtigsten Lücken, mit Aufwand

Reihenfolge nach Hebel für die Optimierung: Was blockiert die meisten Entscheidungen in Abschnitt 2?

1. **Host-Spuren dauerhaft und klonfähig machen.** Phasenstarts, `phases.jsonl` und `process-gate-events.jsonl` nach dem Muster von `report.py --sync` als Blob unter `refs/process/<art>/<host>` veröffentlichen. `PK` liest sie dann wie die Reports (`tower.py --remote`). Das betrifft 2.1-S, 2.3-S, 2.4-S, 2.6-S, 2.7, 2.9, 2.10 und den monatlichen CI-Lauf. **Aufwand: M** (≈ 2–3 Tage; Tier 2, weil es neue Ref-Formate gibt; ein Writer je Datei, Leser in `PK:1645/1659/2956`). Eigentümer bleibt `PK`; die Formate selbst ändern sich nicht.
2. **Zeit je Phase und Übergabe statt Summe.** In `flow_items` die vorhandenen Spannen (`PK:2131-2146`) je Phase ausgeben: Klärung, Plan, Plan-Review, Execute, Fix, Review, Warten aufs Review, Warten auf den Zug, Warten auf den Owner (#319). Dazu braucht Dispatch eine unterscheidbare Plan-Review-Phase (Log-Name `…-plan-review-…` oder ein Report-Feld). Das schaltet 2.3-S, 2.4-S, 2.5-S, 2.8-S und 2.9-S frei. **Aufwand: S–M** (≈ 1–2 Tage; der Phasenname ist ein Format, daher CHANGELOG-Hinweis; alte Logs bleiben `review`).
3. **Geschriebene, aber ungemessene Records lesen.** `ROOT-CAUSE` (Abdeckung je blockierter Runde, `sites: none`-Anteil), `REPLAN` (increment/rebuild je Arbeit), `REFUTE` (Ergebnis) und die Tier-Unterschätzung (Plan-Tier gegen höchstes REVIEW-Tier) als Zeilen in `rounds`/`baseline`/`works`. Es gibt nur Leser; die Grammatik besitzt weiterhin `check_review.py` (TM, „One owner per behavior“). **Aufwand: S** (≈ 1 Tag, keine Format- oder Gate-Änderung).
4. **Test- und CI-Verschwendung sowie Fehlgriffe der Testauswahl (#317).** `test_select.py run` schreibt ein Ereignis (Lane, Dauer, Ergebnis, Timeout, Baum-ID) über `gate_events.append`. Die Train-Zeile bekommt `dropped: [branch…]`. `nodes` und `train-phases` zeigen dann Flakes, Timeouts und Auswahl-Fehlgriffe (2.7-S/G, 2.9-Q). **Aufwand: M** (≈ 2 Tage; berührt Gate-nahen Code, `train.py` ist Tier 3: Refute vor Runde 1).
5. **Review-Ertrag je Kosten (#316) plus Kalibrierungsstichprobe.** Kosten je echtem Blocker, je Reviewer-Familie und Linse, und Leerläufe. Dazu eine kleine, periodische Stichprobe bestandener Runden, die ein unabhängiger Prüfer nachprüft: Fehlende Fänge sind sonst erst als Durchrutscher sichtbar, also 30 Tage später. **Aufwand: M** für #316 (≈ 2 Tage). Die Stichprobe kostet im Projekt ≈ 1 Review-Sitzung pro Woche, kein Template-Code außer einer Triage-Kategorie im Bericht `[assumption: Format offen]`.

Klein und nützlich, aber nicht unter den Top 5: Deploy-Erfolgsquote und Ausschuss je Zug aus vorhandenen Feldern (S, ≈ 2 h). Zeit bis Durchrutscher-Fix (S, ≈ 2 h). Wartezeit bis Start über `gh` (S, ≈ 4 h, braucht Netz wie `outcomes`). Messabdeckungs-Aggregat (S, ≈ 2 h). Wiederherstellungszeit (M: braucht ein Vorfallsformat, Owner-Entscheidung, ob es das geben soll).

**Wohin es gehört.** Alles in `PK` und `TM`, als neue Spalten oder Zeilen der vorhandenen Familien (`flow`, `works`, `rounds`, `baseline`, `nodes`, `train-phases`). Neu ist nur eine Familie `yield` (#316), sofern sie nicht in `rounds` passt. Keine neue Liste außerhalb, kein Gate. Die Tabelle in Abschnitt 2 ist eine Lesehilfe, die auf die Familien zeigt. Wird ein Teil umgesetzt, gehört die Schritt→Familie-Zuordnung als kurzer Abschnitt in `TM`, nicht in dieses Dokument.

## 5. Kenni-Spalte nachprüfen (für einen Agenten mit Zugriff)

Im Kenni-Klon, read-only:

```bash
uv run scripts/process/process_kpis.py baseline --window 2026-09-01:2026-11-01   # population-Zeile, Tier-Tabelle
uv run scripts/process/process_kpis.py rounds | head -60                           # FINDING "not read"?, at=-Abdeckung
git log --since=2026-09-01 --grep='Regression-of:' --oneline | wc -l               # Trailer-Nutzung
test -f .process-work/gate-triage.jsonl && wc -l .process-work/gate-triage.jsonl
git grep -c 'ROOT-CAUSE work=' ; git grep -c 'REPLAN work='
# Host (Steward-Rechner): ls "$(git rev-parse --git-common-dir)"/{process-dispatch,process-train,process-tower}; wc -l "$(git rev-parse --git-common-dir)"/process-gate-events.jsonl
```

## 6. Vergleich mit Draft-PR #356

Siehe Nachtrag unten; geschrieben, nachdem die Abschnitte 1–5 standen.
