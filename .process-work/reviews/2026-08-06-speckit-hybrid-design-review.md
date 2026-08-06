# Independent design review — Spec Kit hybrid + lean teardown (2026-08-06)

Reviewer: independent agent (fresh context, non-implementing), adversarial
prompt; full findings relayed to the owner. Verdict: **viable with
conditions**. Summary of findings and their disposition in SP56:

- F1 (BLOCKER, sequencing destroys the measuring base): superseded by the
  owner's decision to build the end state directly; CFR retained (F2).
- F2 (BLOCKER, teardown deleted the design's success metric): **adopted** —
  telemetry keeps CFR as the third KPI.
- F3 (BLOCKER, overrides are full forks; "tests optional" lives in the skill
  body): **adopted** — overrides minimized (spec + tasks), upgrade-diff
  ritual documented, deterministic checks added: check_speckit (test task
  per story phase) and the SC accounting in publish_and_prune.
- F4 (MAJOR, no escape hatch on a 0.x standard): **adopted** — the fallback
  path stays (frozen), exit scenario documented (freeze the pin; vendored
  state runs without network or CLI).
- F5 (MAJOR, prune not coupled to publish success): **adopted** —
  publish_and_prune verifies the posted comments before deleting; failure
  degrades to flow-forward, loudly.
- F6 (MAJOR, small-model thesis unmeasured): **adopted as framing** — model
  routing documented as a recommendation to be measured against the
  project's own baseline (convergence, cost, CFR).
- F7 (MAJOR, review condensation loses the solo guarantee; SC lifecycle
  unenforced): **adopted** — digest binding kept per REVIEW line (verified
  by the gate), certificate ritual dropped; SC accounting enforced by the
  merge ritual.
- F8 (MAJOR, branching/feature.json unaddressed): **adopted** — branch =
  spec-dir name, feature.json gitignored, git extension not installed;
  documented in the module doc.
- F9–F13 (MINOR): AC-5 became a rendered-file guarantee plus documented
  re-init ritual; EARS sync direction documented (spec authors, issue
  carries the copy); story terminology unified on the inventory; the
  Windows/bash consequence and doc-teardown cost acknowledged in the
  decision documentation.

REVIEW work=speckit-hybrid-design tier=3 reviewer=fresh-agent model=same independence=non-implementing,single-family verdict=block round=1
(verdict block = "viable with conditions"; conditions addressed in SP56, see
CHANGELOG. Recorded here as the audit trail; this repo is the template
source, not a rendered instance — no gate consumes this file.)
