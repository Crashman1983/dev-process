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
| Q | **Ausschuss je Zug** | Anteil der Läufe mit `result=red`; Branches an Bord minus gelandete | %; n | ↓ | `phases.jsonl` (`train.py:1349-1352`) | rote Läufe measured (`train-phases`, `PK:1600-1602`); entfernte Branches data-only | `[assumption]` Host (281 Train-Merges belegt in Git, `2026-10-28-v2.80.md:11`) |
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

Klein und nützlich, aber nicht unter den Top 5: Deploy-Erfolgsquote und entfernte Branches je Zug aus vorhandenen Feldern (S, ≈ 2 h). Zeit bis Durchrutscher-Fix (S, ≈ 2 h). Wartezeit bis Start über `gh` (S, ≈ 4 h, braucht Netz wie `outcomes`). Messabdeckungs-Aggregat (S, ≈ 2 h). Wiederherstellungszeit (M: braucht ein Vorfallsformat, Owner-Entscheidung, ob es das geben soll).

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

Geschrieben, nachdem die Abschnitte 1–5 standen (Commit `adee759`). #356 (`4dd12cc`) liefert `docs/analysis/2026-11-01-schritt-kpis.md`, eine Registry `docs/analysis/step-kpis.json` (17 Schritte, 48 KPIs) und `tests/test_step_kpis.py`. Beim Gegenlesen von #356 fiel ein eigener Fehler auf: `train-phases` gibt rote Läufe schon aus. Ich habe 2.9-Q korrigiert.

### Was #356 besser hat oder was ich übernehme

- **Kenni-Audit.** #356 hatte Kenni-Zugriff. Seine Befunde (kein `process-dispatch`- und kein `process-train`-Verzeichnis, kein Gate-Log, `process-tower` ohne Berichte, 2 `Regression-of`-Trailer auf 106 Merges, keine Deploy-Stufe, `losses` mit n = 28 bei 0 befüllten Werten) beantworten viele meiner `[assumption]`-Zellen. Ich übernehme sie als *Angaben von #356, von mir nicht geprüft*.
- **Messfehler D1–D3**, im Template gegengeprüft:
  - **D1** stimmt: `session_output_tokens` (`PK:138-150`) summiert jeden Regex-Treffer, der Leser in `dispatch.py` (`_transcript_usage`, um `dispatch.py:1360`) zählt je Nachrichten-ID.
  - **D2** stimmt: `losses` bildet die Konfidenz aus `t["issues"]`, nicht aus befüllten Werten (`PK:2357-2359`).
  - **D3** stimmt: `gate_events.append` verschluckt jede Ausnahme (`SP/gate_events.py:46-47`). Das ist gewollt („loses an observation, never a verdict“), aber der Verlust bleibt unsichtbar.
  - **D4** stimmt nur halb. Dass `report` `rounds`, `models`, `outcomes` und `train-phases` auslässt, ist dokumentiert (`TM:79-82`). Dass `cost(None)` ohne Transkripte läuft, stimmt (`PK:3111`).

  Diese Defekte gehören **vor** meine Lücke 1, weil sie Zahlen zu sicher erscheinen lassen. Aufwand jeweils S.
- **Weitere Schritte, die ich nicht hatte:** Dispatch-Modellwahl, Pre-Push-Overrides (`PROCESS_SKIP`) und Housekeeping. Override-Protokollierung (I7) halte ich für nützlich, als Gegen-KPI zu 2.7 („Gates schneller“ durch Überspringen).

### Wo wir uns unterscheiden und warum ich bei meiner Sicht bleibe

1. **„Fehlt in Kenni“ gegen „liegt nicht im Repository“.** #356 schließt aus fehlenden Verzeichnissen, dass Dispatch-, Zug- und Gate-Daten in Kenni „ganz fehlen“. Diese Dateien liegen aber per Konstruktion im Git-Common-Dir des ausführenden Rechners, nicht im Repository (Abschnitt 1: `report.py:12`, `train.py:67`, `gate_events.py:3`). Git belegt mindestens 281 Train-Merges in Kenni (`2026-10-28-v2.80.md:11`). Züge liefen also, ihre `phases.jsonl` liegt nur nicht im geprüften Checkout. Die richtige Folgerung ist meine Lücke 1, ein Template-Mangel: die Spuren sind nicht klonfähig. „Kenni instrumentiert nicht“ wäre der falsche Schluss. Prüfen lässt sich das auf dem Steward-Rechner mit dem `ls` aus Abschnitt 5 `[assumption: noch offen]`.
2. **Keine zweite Wahrheit.** #356 legt eine eigene Registry mit Test unter `docs/analysis/` an und fragt, ob sie ins Template wandern soll (mit Cockpit-Befehl `steps`). Der Auftrag sagt, Owner jeder Messgröße seien `process_kpis.py` und `telemetry.md`. Eine Registry mit 48 Einträgen, eigenen Statuswerten und eigenem Test veraltet neben dem Cockpit, sobald eine Familie sich ändert. Ich schlage stattdessen vor: neue Werte als Zeilen und Spalten der bestehenden Familien und eine kurze Schritt→Familie-Zuordnung in `TM` (Abschnitt 4). Der Test in #356 prüft Form und Pfade, nicht ob die Werte stimmen. Das sagt #356 selbst.
3. **Status „measured“ heißt hier „das Cockpit wertet es aus“.** #356 führt etwa `ROOT-CAUSE-Blöcke je Arbeit` (S7.q2) als `measured`, Quelle „ROOT-CAUSE-Blöcke im Journal“. Kein Code im Cockpit liest ROOT-CAUSE, REPLAN oder REFUTE: `grep -c` in `PK` ergibt 0. Die Daten liegen vor, gemessen wird nichts. Bei mir heißt das `missing (data-only)` und ist Lücke 3. Die Unterscheidung zählt für den optimierenden Agenten: `data-only` heißt, es fehlt ein Leser (S). `measured` würde heißen, es gibt schon Zahlen.
4. **Sparsamkeit.** #356 hat 48 KPIs, davon nur 2 Gegenkontrollen. Ich habe 12 Schritte mit je genau Q, S und G, also 36 KPIs. Jede nennt die Entscheidung, für die sie gebraucht wird. Gegen-KPIs sind bei mir Pflicht je Schritt, weil eine einseitige Optimierung genau dort sichtbar werden muss. Bei #356 ist das nur eine Leseregel („Regeln für den optimierenden Agenten“, 1). Kosten (Tokens) führe ich unter S, nicht als vierte Dimension, weil die Optimierungsziele Qualität und Geschwindigkeit sind und Tokens in `losses` nie mit Zeit summiert werden (TM, `losses`).
5. **Fundorte.** #356 nennt als Quelle meist Datensatznamen ohne Zeile, etwa „phases.jsonl“. Ich nenne Datei:Zeile des Schreibers und des Lesers, damit ein Agent jede Aussage prüfen kann.
6. **Tier-Feld.** #356 schreibt (S1.q1), das Tier sei „als Text im Plan oder Issue notiert, nicht als Feld“, und schlägt ein Feld vor (I4). Pläne tragen aber eine `tier:`-Zeile, die `PK` liest (`_work_tier`, `PK:1062-1073`), und `REVIEW`-Zeilen tragen `tier=`. Die Tier-Unterschätzung lässt sich also schon heute aus Git berechnen (meine 2.2-G, Aufwand S). Ein neues Feld braucht es nicht.
7. **REVIEW-Zeitstempel (I5).** #356 will das REVIEW-Format um Zeitstempel erweitern, das ist eine Vertragsänderung. Die Review-Latenz lässt sich ohne Formatänderung aus Commit-Zeiten der Attest-Commits und aus `pushed`/`review-pass`-Reports bilden, sobald Lücke 1 die Reports klonfähig macht. Ich würde die Vertragsänderung erst angehen, wenn das nicht reicht.

### Gemeinsam

Beide sehen dieselben Kernlücken:

- Tokens und Zeit je Phase (#356 I1, I6; hier Lücke 2)
- Plan-Review-Kosten
- Deploy und Wiederherstellung
- Owner-Zeit statt Owner-Zeilen (#319)
- Trailer-Disziplin als Schwachstelle der Nachfehler-KPI

Gemeinsam ist auch die Regel, nur innerhalb eines Projekts und über die Zeit zu vergleichen.

## 7. Diskussion mit der Sitzung „dev-process optimierung“, Runde 1

Die Gegenseite (Nachricht vom 2026-11-01) bringt Kenni-Zahlen aus dem Fenster 10.–31.10. mit, die ich nicht prüfen kann (`[assumption]`, Angabe der Gegenseite):

- 17 von 311 Arbeiten brauchten ≥ 4 Runden; der Median liegt bei 1–2 Runden.
- Die stärksten Treiber sind > 1.500 Produktzeilen und mehrere Stacks.
- 112 von 158 Blocker/Major-Befunden der Ausreißer tragen kein `origin=`.
- Die Token-Werte in `losses` sind leer; die Prozessversion wird erfasst, aber nicht ausgewertet.

Im Template geprüft:

- `_dispatch_codex.py:466-478`: Das Codex-Befundschema hat kein `origin`, und `additionalProperties: false` verbietet es. Codex-Berichte *können* `origin=` also gar nicht liefern.
- `check_issues.py.jinja:235`: `origin=` ist optional.
- `PK:2202, 2264`: `process_version` steht nur in der `flow`-Ausgabe je Issue; `baseline` und `works` gruppieren nicht danach.

**Wo ich der Gegenseite folge und meinen Entwurf ändere**

1. **Ausreißer statt Median.** Wenn ~5 % der Arbeiten den Großteil der Kosten tragen, verdecken meine Median-KPIs (2.2-S, 2.6-S, 2.8-S) das Problem. Neu je Schritt mit S-KPI: der **Anteil der Runden, Tokens und Produktzeilen, der auf Arbeiten mit ≥ 4 Runden fällt**, neben dem Median. Das gehört als Zeile in `works`/`baseline`. Aufwand S, die Daten liegen vor.
2. **Befund-Datenqualität zuerst.** Ohne `origin=` sind meine 2.5-Q und 2.6-Q bei den Ausreißern blind. Mein Gegenvorschlag zum *Wie*: `origin` nicht nur verlangen, sondern wo möglich **ableiten**. `at=` ist ab v2.78 für Blocker/Major Pflicht. Die Old-Code-Messung (`PK:931-1022`) weiß damit schon, ob eine Blockerzeile seit Runde 1 unverändert ist (≈ `late`) oder vom Fix der Vorrunde berührt wurde (Kandidat `fix`). Ein abgeleitetes `origin` ist mechanisch und entlastet den Reviewer; das erfragte bleibt Urteil, beide getrennt ausweisen. Dazu `origin` ins Codex-Schema. Aufwand S–M; das Schema ist ein Format, also ein CHANGELOG-Hinweis.
3. **Follow-up-Last** übernehme ich als zweite Gegen-KPI in 2.8: `action=follow-up`-Befunde je Arbeit und der Anteil davon, der nach N Tagen noch offen ist (`gh`). Sie macht sichtbar, wenn Runden gespart werden, indem man Blocker in Folge-Issues verschiebt.

**Wo ich widerspreche**

4. **Vorher/Nachher je Prozessversion, aber nicht je Versions-String.** Kenni hat in ~10 Tagen v2.77 bis v2.80.1 durchlaufen; je Version kommen zu wenige Arbeiten zusammen (`thin` < ~20, TM), und Versionswechsel fallen mit Arbeitsmix und Zeit zusammen. Vorschlag: **je Mechanismus ein Fenster vor und eines nach seiner Übernahme** (Datum aus der Historie von `.copier-answers.yml`, Leser `_process_version` `PK:1709`), verglichen mit `baseline --window A --window B`, das zwei Fenster schon kann. Dazu die Konfundierer pro Fenster mit ausweisen: Größenmix, Tier-Mix, Mehr-Stack-Anteil. Aufwand S.
5. **Größe und Stacks sind Korrelation, kein Hebel an sich.** v2.80 hat dafür schon Empfehlungen (R1 Schnittgröße, R2 Schnitt an der Stack-Grenze). Die eigentliche Frage ist jetzt, ob R1/R2 wirken, also Punkt 4. Dafür sollten Ausreißer zusätzlich nach `REPLAN increment|rebuild` gelesen werden (meine Lücke 3): Ab dem zweiten blockierten Runde ist REPLAN Pflicht, also markiert es genau die Ausreißer und sagt, ob der Plan oder die Umsetzung versagt hat.
6. **Host-Spuren bleiben auf der Liste, aber weiter hinten.** Für Kenni ist die Durchlaufzeit kurz (Median 5,5 h, `2026-10-28-v2.80.md:17`), das Problem ist also Menge, nicht Warten. Ich stufe deshalb meine Lücken 1–2 (Host-Spuren, Zeit je Phase) hinter die Datenqualität zurück. Ganz streichen würde ich sie nicht: Der Auftrag nennt Geschwindigkeit als Ziel, und der monatliche CI-Lauf sieht heute keine einzige Zeit- oder Token-Zahl. Leere Tokens in `losses` können zwei Ursachen haben: fehlende Host-Daten oder ein in Kenni nicht gesetzter `transcripts`-Glob in der Policy (`model-policy.json`, `transcripts`). Das muss vor einer Template-Änderung geklärt werden `[assumption: offen]`.
7. **D3:** Ich bin einverstanden, dass das Verschlucken bewusst ist. Sichtbar machen kostet aber nichts am Urteil: Ein Zähler verlorener Schreibversuche (stderr oder eine Ersatzdatei) ändert kein Verdikt. Das ist niedrig priorisiert, ich halte es nicht für erledigt.

**Revidierte Reihenfolge (Vorschlag zur Einigung)**

| # | Was | Aufwand |
|---|---|---|
| 1 | Befund-Datenqualität: `origin` ins Codex-Schema, aus `at=` ableiten, abgeleitet und erfragt getrennt | S–M |
| 2 | Messfehler D1 (Token-Doppelzählung) und D2 (Konfidenz nach befüllten Werten) | S |
| 3 | Ausreißer-Anteil (Runden, Tokens, Zeilen bei ≥ 4 Runden) in `works`/`baseline`, mit REPLAN- und ROOT-CAUSE-Lesern | S |
| 4 | Vorher/Nachher je Mechanismus-Übernahme mit Mix-Angaben | S |
| 5 | Follow-up-Last als Gegen-KPI zum Review | S |
| 6 | Host-Spuren klonfähig und Zeit je Phase, nach Klärung des `transcripts`-Globs | M |

## 8. Kenni-Prüfung (nachgetragen, Kenni-Zugriff ab 2026-11-01 abends)

Gelesen wurde Kenni `main` @ `19b7b02` (Template v2.80.0, volle Historie, 19.924 Commits seit 2026-04-11). Ich habe nur mit `git`/`grep` und einem eigenen Lese-Skript ausgewertet. Kenni-Code lief nicht: Das Ausführen von Kennis `process_kpis.py` hat der Auto-Mode abgelehnt. Die Werte unten sind deshalb **meine Zählung**, nicht die Ausgabe des Cockpits.

Fenster: Datum aus dem Dateinamen der Journal-Shards. Monatsarchive zählen ganz zum Monat.

| Prüfpunkt | Befund | Folge für die KPI-Tabelle |
|---|---|---|
| Host-Dateien (`process-dispatch/`, `process-train/`, `process-tower/`, Gate-Log) | per Konstruktion nicht im Klon; der Steward-Rechner ist von hier nicht prüfbar | alle Host-Zellen bleiben `[assumption]` |
| Tokens (`transcripts`) | kein `transcripts`-Schlüssel in `model-policy.local.json` oder `model-policy.codex.local.json` | **Projekt-Lücke:** Die leeren Tokens in `losses` kommen (auch) von der fehlenden Konfiguration; I1 aus #356 und meine Lücke 1 lösen das allein nicht |
| Mandat `optimization.local.json` | fehlt | `outcomes`-Marker, `deploy`, Guardrails und `plan_drift`-Modus stehen auf Standard; ohne Mandat startet laut `optimization.md` kein Versuch |
| `gate-triage.jsonl` | fehlt | 2.7-Q (bestätigte Fänge) ist in Kenni **nicht messbar**, das Regel-Budget bleibt „unbekannt“ |
| `Regression-of:`-Trailer | **2** in der ganzen Historie, gegen 316 `fix:`- und 243 `feat:`-Commits seit 10.10. | 2.2-Q und 2.11-Q (Nachfehler) sind praktisch blind; nur der `cfr`-Proxy trägt. **Projekt-Lücke**, die Grammatik ist da |
| Code-Review-Runden (eigene Zählung, `REVIEW`-Zeilen, ohne `-plan`) | 10.–31.10.: 181 Arbeiten, Median 1, P90 3, ≥ 3 Runden: 20, ≥ 4: 13; **28 % aller Runden** entfallen auf diese 13 (7 %). 1.9.–31.10.: 262 Arbeiten, ≥ 4: 23, 29 % der Runden | bestätigt die Ausreißer-These der Gegenseite. Deren 311 Arbeiten / 17 Ausreißer zählen anders (vermutlich gemergte Arbeiten aus Git); Größenordnung gleich |
| Tier-Mix (dieselben 181) | Tier 3: 95, Tier 2: 66, Tier 1: 20 | über die Hälfte Tier 3, obwohl `risk-tiers.md` vor unnötigem Tier 3 warnt; 2.2-S/G zählen hier besonders |
| Tier-Unterschätzung (2.2-G) | 7 von 178 Plänen mit `tier:` und Code-`REVIEW` haben ein höheres REVIEW-Tier | aus Git messbar, wie behauptet; selten. Die Richtung ist eher Über- als Untereinstufung |
| `ROOT-CAUSE` je blockierter Code-Runde (2.6-G) | 135 von 226 (60 %) | Daten liegen vor; 40 % ohne Ursache, ein Leser lohnt sich |
| `REPLAN` bei ≥ 2 blockierten Runden (2.4-Q) | 6 von 47 Arbeiten | Pflicht in der Doku, kaum befolgt (die Regel ist jung, `CHANGELOG.md:162`); als Ausreißer-Marker taugt REPLAN in Kenni **noch nicht**, mein Punkt 7.5 ist damit abgeschwächt |
| `origin=` bei Blocker/Major (2.5-Q, 2.6-Q) | gesamt 399 von 662 (60 %); **Codex-Berichte 4 von 137 (3 %)**, übrige 395 von 525 (75 %) | bestätigt die Gegenseite und den Schema-Befund (`_dispatch_codex.py:466-478`): die Lücke ist fast ganz Codex, also **Template** |
| `at=` bei FINDING-Zeilen | 877 von 3.513 | Old-Code-Messung (2.8-Q) und das vorgeschlagene abgeleitete `origin` gehen nur für etwa ein Viertel der Befunde. `at=` ist erst seit v2.78 (25.10.) Pflicht, die Basis wächst |
| `action=follow-up` | 786 von 3.513 Befunden (22 %) | die Follow-up-Last (7.3) ist groß genug, um als Gegen-KPI zu zählen |
| Template-Versionswechsel | 15 Updates zwischen 10.10. und 28.10. (v2.70.0 → v2.80.0) | bei rund 180 Arbeiten im Fenster etwa **12 Arbeiten je Version**, unter der `thin`-Schwelle (~20). Das stützt 7.4: Vergleich je Mechanismus über Fenster, nicht je Versions-String |
| Messmeilensteine | `milestones.local.json` mit 2 Einträgen; `plan-drift-2026-10-27` fällig, kein `.process-work/optimizations/` | 2.12-S misst in Kenni bereits eine überfällige Messung |
| Deploy | Kenni hat kein Mandat mit `deploy`; ob `train --deploy` genutzt wird, ist aus dem Klon nicht sicher (`Makefile` nennt `--deploy` einmal) | 2.10 bleibt `[assumption]`; #356 sagt „keine Deploy-Stufe“ |

**Was sich an der Reihenfolge (7) ändert:**

1. `origin` im Codex-Schema bleibt **Platz 1** und ist jetzt belegt: 3 % gegen 75 %. Aufwand S. Das abgeleitete `origin` aus `at=` stufe ich auf „später“ zurück, weil `at=` erst ein Viertel abdeckt.
2. **Neu weit oben: Projekt-Konfiguration in Kenni** (kein Template-Code): `transcripts`-Glob setzen, `optimization.local.json` anlegen, `gate-triage.jsonl` beginnen, `Regression-of:` in `fix:`-Commits durchsetzen (das schreibt `commits.md` schon vor). Aufwand je unter einer Stunde, dazu laufende Disziplin. Ohne das bleiben Tokens, Nachfehler und Gate-Wert in Kenni leer, egal was das Template baut. Umsetzen muss das der Kenni-Steward, nicht dieser PR.
3. D1/D2, Ausreißer-Anteil und Follow-up-Last unverändert (S).
4. REPLAN- und ROOT-CAUSE-Leser bleiben S, sind aber als *Disziplin-KPI* zu lesen (60 % bzw. 13 % Befolgung) und noch nicht als Ausreißer-Diagnose.
5. Host-Spuren klonfähig machen (M) bleiben hinten. Ob sie auf dem Steward-Rechner vorliegen, kann nur jemand mit Zugang zu diesem Rechner prüfen.
