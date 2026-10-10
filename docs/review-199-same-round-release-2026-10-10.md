# Release-phase review — #199 same-round follow-up

DECISION 2026-10-10 Codex: publication phase of existing6fab082d source; no parallel implementation or modification of the original owner's checkout. Increment versus rebuild: keep existing superseded_records owner; the violated expectation is attest's equal-round PASS arithmetic, corrected narrowly under unchanged work/fork/ancestry/standing-block guards. No additional gate authority.

REFUTE work=199-same-round round=1: survives — fresh non-implementing tools-on reviewer,9 permanent regression cases and11 full Git/main-push probes, meaningful guard mutant pristineGREEN→ASSERTIONRED→restoredGREEN. Exact report below.

Actual verification: targeted tests/test_review.py98/0; immutablebase with new regression only1ASSERTION failure/3pass. Canonical tools/release.py v2.62.1 without --no-suite: Ruff0; full bumped-tree pytest1818/0 in359.91s. Release commit87606a0 changes only6 expected metadata/version/SBOM files (11+11). Sourcehashes from independent refute unchanged. No runtime change in release bump.

Two actual fresh CLI reviewers returned PASS, no independently confirmedHIGH/CRITICAL≥80. Claude tools-off Opus5.5 is the same family as original implementer, so earns bundle,non-implementing only; actual read-only Codex CLI is cross-model to originalClaude implementation. No fabricated attestation writer: this upstream repository has no installed own process and uses existing tools/release.py PR/rebase/CI/tag/publish route.

Portable PR CI is required before rebase merge; CI on exact merged mainSHA is required before tag/publish. Neither merge/tag/publication is claimed here; those outcomes are checked in the workflow/PR record. Revert can undo source; released version is immutable and would need a subsequent release. Blast radius: portable review gate downstream pushes.


## Independent refute

# Independent adversarial refute — dev-process #199 same-round correction

Verdict: **SURVIVES**. No independently confirmed HIGH/CRITICAL blocker.

Scope: immutable implementation commit `6fab082d16960e7d0ac988f817e457bf98f202d1`, compared with release/main `01c1b389f58b230b58dc1507294567f8d56194c4`. Refuter did not implement this source. Read-only repository inspection and execution; all custom fixture repositories, scripts and mutants were created under the refuter's own `/tmp` paths. Root concurrently prepares release metadata in its clone; that metadata is outside this source assessment.

## Source provenance

Linux repository `/tmp/dev-process-199-release-codex`:

- `template/scripts/process/check_review.py`: SHA256 `623e2b39cbcf9c1391b332a4d28f41a3e5f5fa334a8c61ce23c87cf39b0551d4`.
- `tests/test_review.py`: SHA256 `5896bea861fbb45c16f6315631a845c8035a94dcd4c07798561eeb64862251af`.

Hashes remained unchanged after all refute runs. Refuter did not edit the repository, index, branches, tags, PRs or external threads.

## Permanent regressions

Actual command, cwd the Linux clone:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_review.py -k "same_number or unfit_round or superseded_off_fork_pass or does_not_descend" --basetemp=/tmp/dev-process-199-refute-pytest
```

Result: **9 passed, 89 deselected, 12.30s**, process exit 0. Raw log `/tmp/dev-process-199-refute-pytest.log`.

## Fresh full-gate probes

`/tmp/dev-process-199-refute-probe.py` imports the immutable test helpers and actual template gate, creates separate real Git histories, commits its journal records, sets the real `PROCESS_PUSH_TARGETS=refs/heads/main`, and runs `check(root)`. No stubbed Git facts or invented private-state injection.

Actual command:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python /tmp/dev-process-199-refute-probe.py
```

**11 scenarios completed, process exit 0**; raw result and fixture paths `/tmp/dev-process-199-refute-probe.log`.

| Scenario | Hard findings | Result |
|---|---:|---|
| Valid same-round PASS | 0 | Old off-fork line becomes a note |
| Same-round BLOCK | 3 | Refused; does not supersede |
| Tier-3 PASS with only `bundle` | 2 | Independence arithmetic refuses the push |
| Tier-1 PASS for a Tier-2 archived plan | 1 | Plan has no clearing review |
| Unrelated work ID | 2 | Refused; does not supersede |
| Later record itself off-fork | 3 | Refused; does not supersede |
| Nonancestor review head | 1 | Refused; does not supersede |
| Lower round | 1 | Refused; does not supersede |
| Reverse journal order, valid descending PASS | 0 | Accepted by immutable Git ancestry, independent of shard order |
| Old off-fork BLOCK plus same-round valid PASS | 1 | Committed standing block remains hard |
| Valid same-round PASS followed by round-3 BLOCK | 1 | Later committed block remains hard |

Weak independence and wrong tier can soften the obsolete malformed-line finding, but do not clear their independent enforcement requirements. Source trace: `_arithmetic_violations` is added to hard findings before superseding; plan coverage requires the appropriate tier; `standing_block_findings` reads committed history and `latest_verdicts` gives BLOCK priority at equal rounds. `superseded_records` has only its gate call site, not a separate unchecked release authority.

Record order is intentionally not a global authority: journal shards have no global sequence. The later full review's head must descend from the old reviewed head and start at its own valid fork point. Reversing textual line order does not bypass either fact.

## Meaningful scratch mutant

`/tmp/dev-process-199-refute-mutant.py` copies only the gate into separate scratch paths, retaining immutable imports. It runs the permanent same-round-BLOCK regression:

- Pristine: **GREEN**.
- Mutant removes only `v["verdict"] == "pass"` from the equal-round condition: **ASSERTION RED** (the obsolete line incorrectly becomes a note).
- Restored source: **GREEN**.

Process exit 0; raw `/tmp/dev-process-199-refute-mutant.log`. This is a compiled/imported production-code mutant with the unchanged permanent assertion, not a mirrored implementation assertion.

## Excluded preparation attempts and limits

Two early custom-fixture preparation attempts are excluded from scored evidence: one changed its archived plan before checking out another branch, causing a Git checkout refusal; another left journals uncommitted and therefore did not exercise the documented committed-history standing-block owner. The final probes committed their journals and ran pristine controls before conclusions. Neither was an implementation RED or a blocker.

This report proves the changed gate's specified failure classes. It does not claim the full release suite, portable CI, release version bump, tag, publication, downstream Kenni update or deployment. Those remain Root's separate release sequence.


## Claude raw completed report

# Unabhängiges Tier-3-Release-Review: dev-process #199, Nachtrag mit gleicher Rundennummer

**Geprüft:** base `01c1b389f58b230b58dc1507294567f8d56194c4` → head `6fab082d16960e7d0ac988f817e457bf98f202d1`

**So habe ich geprüft:** ohne Tools, nur lesend und nur aus dem Paket (Diff, Code-Kontext, Tests, Refute-Bericht, Prozessdokumente). Ich habe nichts geändert und nichts ausgeführt.
- Aussagen zum gezeigten Diff und Kontext sind am Paket belegt.
- Alles zum übrigen Repo (`standing_block_findings`, `latest_verdicts`, `_arithmetic_violations`, Aufrufstellen) ist **[assumption]**. Diese Teile stützen sich auf den Refute-Bericht; den Quelltext dazu habe ich nicht gesehen.

## Befunde

**Keine bestätigten HIGH/CRITICAL-Befunde mit Konfidenz ≥ 80.**

### Geprüfte Angriffsflächen ohne blockierenden Befund

1. **Wie weit die Änderung reicht.** Die Änderung erweitert nur eine Bedingung in `superseded_records`. Das `invalid`-Dict selbst bleibt unverändert.
   - `valid_passes`, die Plan-Abdeckung und der Train lesen weiterhin über `invalid_records`. Eine abgelöste Zeile gibt also weiterhin nichts frei.
   - Im schlimmsten Fall wird ein harter Befund „malformed REVIEW line“ zu einer Notiz. Es entsteht keine neue Freigabe.
   - Dass `superseded_records` nur diese eine Aufrufstelle im Gate hat, ist **[assumption]** aus dem Refute.
2. **Selbst-Ablösung.** `later` schließt alle Records in `invalid` aus. Eine ungültige Zeile kann sich also weder selbst ablösen noch durch eine andere ungültige Zeile abgelöst werden. Das ist im Paket belegt.
3. **Reihenfolge und Abstammung.**
   - **Beispiel:** Ein gültiger Pass in Runde N auf Head H1 kommt zuerst, danach folgt eine off-fork-Zeile in Runde N auf H2, die von H1 abstammt. H2 ist kein Vorfahr von H1, also wird die Zeile nicht abgelöst. Ein älterer Pass kann eine jüngere Zeile damit nicht verdecken.
   - **Gleicher Head:** Bei `r.head == v.head` liefert `--is-ancestor` true. Dann ist die Zeile tatsächlich vollständig von v abgedeckt, die Notiz ist also korrekt.
   - **Textreihenfolge:** Die umgekehrte Reihenfolge der Zeilen wird im Refute geprüft und ist unkritisch, weil Git-Abstammung die Autorität ist und nicht die Shard-Reihenfolge.
4. **Block bei gleicher Runde.** Nach einem Pass kann bei gleicher Rundennummer auch ein Block folgen (Zählweise 1 + Blocks). Den lehnt die neue Bedingung ab: `verdict == "pass"` ist ausdrücklich gefordert.
   - Der parametrisierte Test `same-round-block` deckt das ab.
   - Laut Refute macht ein Mutant, der genau diese Bedingung entfernt, den Test ROT.
   - Dass eine ungültige Block-Zeile, die als Notiz abgelöst wurde, über `standing_block_findings` und den Block-Vorrang in `latest_verdicts` weiter hart bleibt, ist **[assumption]** (Refute-Probe: 1 harter Befund).
5. **Schwache Unabhängigkeit oder falsche Tier.** Die ablösende Runde v wird in `superseded_records` nicht auf Tier oder Unabhängigkeit geprüft.
   - Das ist vor dem Fix schon genauso, beim Pfad über die höhere Runde.
   - Unabhängigkeit und Tier werden an anderer Stelle durchgesetzt (Arithmetik, Plan-Abdeckung). Das ist **[assumption]** aus dem Refute.
   - Siehe Residual R1.
6. **Fremde Arbeit, niedrigere Runde, v selbst off-fork, v ohne Abstammung.** Alle diese Fälle bleiben unverändert hart. Eine Kombination aus Bestandstests und neuen Tests deckt sie ab.

### Residuals (Minor/Nit, nicht blockierend)

- **R1 (Minor, Konfidenz ca. 50, schon vor dem Fix vorhanden).** Ein v mit Tier 1 oder einer schwachen Selbstprüfung kann eine malformed-Zeile zur Notiz machen.
  - Das passiert aber nur bei Arbeit ohne Tier-2+-Plan. Dort war ohnehin kein Review nötig.
  - Die Änderung macht den Fall nicht breiter. Ein Folge-Issue ist optional.
- **R2 (Minor, schon vor dem Fix vorhanden).** v muss nicht im gepushten Bereich liegen. Es reicht ein abstammender Head, auch auf einem Geschwister-Branch.
  - Die eigene Inhaltsabdeckung des Pushs bleibt davon unberührt, also wird nichts freigegeben.
- **R3 (Prozess, Regel 4).** Das ist der zweite Patch an derselben Ablöse-Invariante.
  - Prüfen: Der Plan sollte einen `DECISION`-Eintrag „increment vs. rewrite“ enthalten. Er ist im Paket nicht zu sehen.
  - Das ist ein Plan- und Prozesspunkt, kein Defekt im Code. Nach den Regeln in `verification-independence.md` blockiert er nicht.
- **R4 (Nit).** Der CHANGELOG ist in der Ich-Form geschrieben („Mein Test in v2.62.0…“). Die Position direkt über v2.62.0 passt zur bestehenden Reihenfolge.
- **R5 (Unabhängigkeit dieses Reviews).** Für dieses Review gilt: `bundle,non-implementing`.
  - `cross-model` lässt sich nur eintragen, wenn die Implementierung nicht von einem Claude-Modell stammt. Aus dem Paket geht das nicht hervor.
  - Die Attestierung muss das wahrheitsgemäß setzen, sonst `single-family`.

## Release-Gate

Die Freigabe gilt **nur für den Quelltext**, nicht für das Release.
- Merge oder Release nach main bleibt gesperrt, bis die komplette lint/pytest-Suite auf dem gebumpten Baum und das portable CI grün sind und im Release-Record stehen. Ohne `--no-suite`.
- Die genannten Zahlen (98/0, Base-RED 1+3, Refute 9 passed und 11 Probes) habe ich nicht selbst nachvollzogen; sie sind **[assumption]**.
- Für den Metadaten- und Version-Bump-Commit gilt dieses Review nicht. Er muss Buchhaltung bleiben, sonst ist eine neue Runde nötig.

**Merge-Risiko: gering.** Die Änderung erweitert eine Bedingung, die einen harten Befund nur zur Notiz macht. Die Menge der ungültigen Records, die Freigaben und die Block-Logik bleiben gleich.

## Verdict: **PASS**

`base=01c1b389f58b230b58dc1507294567f8d56194c4 head=6fab082d16960e7d0ac988f817e457bf98f202d1`, mit den Residuals R1 bis R5. Das Release ist erst freigegeben, wenn die volle Suite und das portable CI auf dem Release-Baum grün sind.

## Codex raw completed report

Keine bestätigten HIGH/CRITICAL-Befunde ≥80 % Konfidenz.

[verified: bereitgestellter Code] Die Erweiterung erlaubt bei gleicher Rundennummer ausschließlich `pass`. Gleiches Work, Abstammung des neuen Heads und dessen gültige Fork-Basis bleiben erforderlich. Die alte Zeile bleibt in `invalid`; ihre Herabstufung zur Notiz macht sie nicht zu einem freigebenden Review. Das Verhalten für höhere Runden bleibt erhalten. Die neuen Regressionen prüfen gleichen PASS, gleichen BLOCK, fehlende Abstammung und höheren PASS.

[assumption: vorgelegter Refute-Bericht, hier nicht ausgeführt] Die vollständige Gate-Prüfung hält Independence-Arithmetik, erforderlichen Tier, committed BLOCKs und Review-Abdeckung als eigene Sperren aufrecht. Deshalb kann eine schwache oder falsch eingestufte Runde den alten Formfehler zur Notiz machen, ohne den Push freizugeben. Die beschriebenen adversarial Probes und der PASS-Bedingungs-Mutant stützen diese Trennung. Journal-Reihenfolge ersetzt keine Git-Abstammung.

Residual: Die vollständigen Gate-Aufrufstellen und Release-Ergebnisse sind nicht im Codeauszug enthalten; ihre Bewertung beruht auf dem Bericht. Cross-model-Unabhängigkeit ist im Packet nicht nachgewiesen. Diese Prüfung ist ausschließlich tools-off und nicht implementierend.

Exakt geprüfte Range:
- Base: `01c1b389f58b230b58dc1507294567f8d56194c4`
- Head: `6fab082d16960e7d0ac988f817e457bf98f202d1`

Merge-Gefahr: Dieses Verdict deckt weder spätere Release-Änderungen noch einen Merge oder eine Veröffentlichung vor erfolgreicher vollständiger Lint-/pytest-Suite und portablem CI ab.

**PASS**
