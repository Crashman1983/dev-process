# Abbauliste: Lean-Standardisierung des dev-process

Datum: 2026-08-06 · Entscheidungsvorlage (noch kein Beschluss) · Kontext:
Spec Kit ist als Standard-Spezifikationsweg beschlossen
(`docs/design/2026-08-06-speckit-hybrid-design.md`); diese Liste beziffert,
was darüber hinaus gestrichen, ersetzt oder eingedampft werden kann, um näher
an Industriestandards zu kommen. Zeilenzahlen sind gemessen (Scripts +
zugehörige Tests), nicht geschätzt; Doku-/Template-Zeilen kommen jeweils hinzu.

**Leitfrage je Position:** Existiert ein Industriestandard, den wir nachbauen?
→ ersetzen. Kein Standard, aber Kernwert? → behalten, ggf. eindampfen.
Nische ohne Nachfrage? → streichen.

## Übersicht

| # | Position | Aktion | entfällt (LoC Script+Test) | Aufwand | Risiko |
|---|---|---|---:|---|---|
| 1 | GitLab-CI-Adapter | **streichen** | ~150 + CI-Matrix ×2→×1 | klein | keins (GitHub im Einsatz) |
| 2 | `parity`-Modul | **streichen** | ~385 | klein | Nischen-Feature weg |
| 3 | `feature-registry` + `story_order` | **streichen** → GitHub Issues/Sub-Issues/Projects (via `github-issues`/`github-master`) | ~985 | mittel | Story-Tracking nur noch online-SSOT (Snapshot-Gate bleibt hermetisch) |
| 4 | Issue-Convenience-Views (`attention.py`, `who_is_working.py`) | **streichen** → GitHub Projects/UI | ~540 | klein | HITL-Cockpit weg; Claim-Konvention bleibt als Doku |
| 5 | Eigener Hook-Installer (`install_hooks`, `run_hook`) | **ersetzen** → [pre-commit](https://pre-commit.com)-Framework | ~560 | mittel | neue (Standard-)Dependency |
| 6 | Copilot- + AGENTS.md-Command-Adapter | **streichen** → Spec-Kit-Integrationen decken Agent-Vielfalt; verbleibende Nicht-Spec-Commands nur noch für den gewählten Harness | ~350 + Achse 3→1 | klein | Harness-Wechsel kostet Re-Init statt Umschalten |
| 7 | `contract-first` + `contracts-drift` | **verschmelzen** zu einem `contracts`-Modul | ~135 (Dedup) | klein | keins |
| 8 | Review-Maschinerie (`check_review` 563, `make_review_bundle` 274, Tests 879) | **eindampfen**: artifact-v1-Zertifikate + Digest-Bindung raus; bleibt: einfache `REVIEW`-Attestierung + Tier-Presence + Tier-3-Cross-Model | ~1.100 von ~1.700 | mittel | stärkste Garantie (Diff-exakte Bindung) weg; Basis-Enforcement bleibt |
| 9 | Telemetrie (`process_kpis` 609, `check_telemetry` 237, Tests 615) | **eindampfen** auf die zwei Ziel-KPIs: Konvergenz + Kosten | ~900 von ~1.460 | mittel | Kalibrier-Suite/DORA-CFR weg |
| 10 | Profile (solo/team) + 13 Modul-Toggles | **kollabieren**: ein opinionated Standard-Setup, fest an; einziger Schalter: „Regulated"-Paket (SBOM + Security-Floor) | Kombinatorik in Tests/Doku | mittel | Flexibilität weg — gewollt |
| 11 | Eingefrorener Fallback (Alt-Commands + `design-template.md`) | **streichen** (Konsequenz aus „Standard, nicht Option") | ~250 | klein | kein Betrieb ohne Spec Kit mehr |
| 12 | Zwei Review-Binding-Modi (legacy vs. artifact-v1) | **auf einen Modus** (folgt aus #8) | in #8 enthalten | – | – |

**Bleibt (der verteidigbare Kern, kein Standard-Äquivalent):** Tier-Routing,
`gate_runner`, Gates: kernel, clarification, doc-drift, decisions,
product-frame, review (schlank), github-issues (schlank) + github-master,
security-floor, SBOM (CycloneDX = Standard), arch-onboarding (delegiert an
import-linter/dependency-cruiser = Standard), arch-docs (arc42/C4 = Standard),
`PRODUCT.md`, ADRs, Journal/Branch-State, DoR/DoD, Spike/Quick/Debug-Flows.

**Netto:** grob 5.000+ LoC weniger (≈ 35–40 % von Scripts+Tests), und —
wichtiger — die Options-Achsen kollabieren: Module 13→~8 fest + 1 Paket,
Harness 3→1, CI 2→1, Profile 2→1, Review-Modi 2→1. Der Pflege- und
Testaufwand skaliert mit den Achsen, nicht mit den Zeilen.

## Detail und Begründung je Position

**1. GitLab-CI** — Vorratshaltung ohne Nutzer. Der `gate_runner` bleibt
CI-agnostisch (ein Subprozess); wer GitLab braucht, ruft ihn in einem
selbstgeschriebenen Job auf. Streichen halbiert die CI-Render-Matrix.

**2. parity** — Capability×Surface-Matrix gegen stillen Capability-Verlust:
konzeptionell schön, praktisch Nische; in keinem der Ziele (Tempo, Kosten,
Fehlerrate) wirksam.

**3. feature-registry** — der Nachbau eines Standards, den wir parallel
nutzen: GitHub Issues/Sub-Issues sind das Story-Tracking der Industrie, und
`github-master` hat die Wahrheitsrichtung schon zu GitHub gedreht (hermetisch
über den committeten Snapshot — der Offline-Gate-Charakter bleibt).
`blocked_by`/`parent`-Prüfungen wandern in den `github-master`-Gate; die
Story→Test-Traceability trägt das EARS-Kriterium im Issue plus Test-Referenz.

**4. attention.py / who_is_working.py** — eigene Dashboards für etwas, das
GitHub Projects nativ rendert. Die Claim-/Heartbeat-*Konvention* (nie
gegatet) bleibt als Doku-Absatz.

**5. Hooks → pre-commit** — gleiches Enforcement, Standard-Werkzeug, das
Contributor bereits kennen; unsere Gates werden ein `repo: local`-Eintrag.
Der Eigenbau (Installer, Launcher-Kompatibilität, 318 Testzeilen) entfällt.

**6. Harness-Achse** — Spec Kit übernimmt die Agent-Vielfalt für die
Spezifikationsphasen; die verbleibenden dev-process-Commands (quick, debug,
execute, review, commit, prime) werden nur noch für den bei `init` gewählten
Harness gerendert statt kombinierbar für drei.

**7. contracts** — zwei Module, ein Thema (Kopplung als geprüfter Contract);
ein Modul mit zwei Prüfmodi spart Doku, Manifest-Key und Testfixtures.

**8. Review-Eindampfung — die heikelste Position, deshalb explizit:**
Die artifact-v1-Kette (tree-empty-Zertifikat, Diff-Digest, Kandidaten-
Bindung) ist technisch die stärkste Garantie im Repo und zugleich die
größte Sonderlocke (~1.700 LoC, eigene Grammatik, eigenes Ritual). Der
GitHub-Standard (Branch Protection + Required Reviews + CODEOWNERS) ersetzt
sie für Teams — aber **nicht für Solo-Betrieb**: GitHub kann die eigene
PR-Freigabe nicht erzwingen, und Cross-Model-Unabhängigkeit kennt es gar
nicht. Deshalb nicht streichen, sondern eindampfen: die einfache
`REVIEW`-Zeile (Presence + Independence-Arithmetik) bleibt als Gate, die
Zertifikats-/Digest-Maschinerie entfällt. Wer die harte Bindung je braucht,
findet sie in der git-Historie dieses Repos.

**9. Telemetrie** — dein Ziel ist „schneller, zielgerichteter, billiger".
Dafür genügen zwei gemessene Größen: Konvergenz (Review-Runden bis pass)
und Kosten je gemergter Änderung. GRADE-Format und Gate bleiben (sonst ist
die Messung Prosa), Kalibrier-Suite und die übrigen KPI-Familien entfallen.

**10/11/12. Options-Kollaps** — ein Standard-Setup, fest verdrahtet; der
einzige verbleibende Schalter ist das „Regulated"-Paket. Der Spec-Kit-
Fallback entfällt ersatzlos: „Standard, nicht Option" zu Ende gedacht.

## Reihenfolge-Empfehlung

**Erst abbauen (SP56), dann den Spec-Kit-Adapter bauen (SP57).** Der Adapter
verdrahtet sich in Review-Gate, Issues und Commands — jede dieser Flächen
wird durch den Abbau kleiner. Umgekehrt hieße es, den Adapter zweimal zu
bauen. Der Abbau selbst ist risikoarm: jede Position ist ein eigener,
atomarer Commit mit grüner Restsuite; nichts geht verloren, was nicht in
der git-Historie bleibt.

## Prozess-Pflicht

Dies ändert den Produktrahmen (bisher: „portabel, harness-agnostisch,
tool-unabhängig" → neu: „GitHub + Spec Kit + pre-commit als Standard-Stack,
dev-process als Enforcement-Kernel"). Der Beschluss wird als Decision Record
(`Type: product`) festgehalten und `PRODUCT.md`/README ziehen im selben
Zug nach (Regel 4 — kein stilles Umsteuern).
