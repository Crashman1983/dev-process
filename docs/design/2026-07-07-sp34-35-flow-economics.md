# SP34 + SP35 — flow closure and economics/discoverability (from the hard audit)

Two follow-up slices from the four-session audit (campaign #14). SP34 closes
the flow/choreography gaps the cold-start adopter hit (#16); SP35 cuts the
read-burden fat and closes the discoverability gaps the economics session
measured (#17). Shipped together; the gate touches are small, the rest is docs.

## SP34 — flow closure (#16)

- **Plan archival has an owner.** `commits.md` names it as a merge step: the
  last commit on the branch (before merge) moves the plan to `plans/archive/`,
  which is the only place the review-presence gate scans — leaving it in the
  active dir made the flagship "no unreviewed Tier 2+ merge" guarantee
  silently unfireable.
- **Baseline commit vs. the hook.** `start-here.md` first-run now names the
  sanctioned `ALLOW_MAIN_COMMIT=1` bypass for the one-time onboarding commit,
  which the `git-hooks` no-direct-main pre-commit would otherwise block.
- **Tracker-less escapes.** A `done` story may carry `issue_waived: <reason>`
  (soft, not the hard done-needs-issue); a `publish-waived:` report exempts its
  follow-up findings from the issue requirement (off-tracker → no issues to
  link). Both close the "unwinnable gate on a tracker-less project" dead-end.
- **Kernel from a neutral file.** `docs/process/kernel.md` always renders and
  carries the `KERNEL:START/END` block, so a brownfield skip-CLAUDE.md install
  can obtain the kernel with no rendered adapter present. BOOTSTRAP points at it.
- **Reviewer grammar.** `/review` now names the exact `REVIEW`/`FINDING` grammar
  a dispatched fresh reviewer must emit, so its output is gate-readable.
- **Tier 1/2 boundary + independence reality.** `risk-tiers.md` qualifies the
  Tier-2 trigger as *depended-upon* (contract/persistence/auth/cross-component),
  not merely user-*visible*, with an explicit Tier-1 example — Tier 1 was nearly
  unreachable. `verification-independence.md` + the `check_review` arithmetic
  now match Quick's reality: Tier 0–1 is the self-check band, Tier 2 is the
  first tier requiring a fresh read-only-bundle review (the bundle/
  non-implementing floor moved from tier≥1 to tier≥2).
- **BOOTSTRAP:** `python3` in the verification block; a version-check step that
  tells an adopter to compare the render to the README and pass `--vcs-ref=HEAD`
  (or wait for a release) on tag skew — the install-tag BLOCKER's doc half.

## SP35 — economics / discoverability (#17)

- **Module docs are discoverable.** The three anchors (CLAUDE/AGENTS/copilot)
  render a zero-drift list of exactly the active modules' docs — previously 8 of
  12 (~12.5k tokens of binding rules) had no pointer anywhere and surfaced only
  on CI failure.
- **`/quick` carries its own operative steps** and says the full workflow.md /
  review-checklist.md need not be read for a small change — cutting the Tier-1
  read burden (measured ~5,340 tokens for a three-line fix).
- **`/prime` reads `.process-work/inbox.md`** — it was write-only ritual that no
  command read back.
- **Which-artifact-when router** in `start-here.md` — a one-page table mapping
  decision/design/product-shape/behavior/plan/journal/inbox/report to its home.
- **Multi-agent honesty.** `journal-state-plans.md` (Parallel efforts) now names
  the three SSOT collisions the sharding does *not* protect (story-ID race,
  PRODUCT.md semantic merge, campaign-parent TOCTOU) instead of the flat "runs
  several efforts cleanly."
- **Mid-size trap named.** `start-here.md` states the three core gates are not
  toggleable, so a minimal-profile project's first Tier 2+ change carries the
  full ceremony without the module infrastructure to house it.

## Deferred (named, not built)

- The `process-gates` job-name-vs-branch-protection nuance (#16 minor),
  gate_runner in-process calls (#17 minor, perf), security-floor repo-size
  scaling (#17 minor) — real but low-value; left for a future perf pass.

## Anchor Delta

SP34: `check_review.py` arithmetic floor tier≥1→tier≥2; `check_issues.py`
story `issue_waived` + report follow-up waiver; `commits.md`, `start-here.md`,
`risk-tiers.md`, `verification-independence.md`, `review.md`, github-issues
module doc; new `docs/process/kernel.md`; root `BOOTSTRAP.md`. SP35: three
anchor templates (module list), `prime.md` + `prime.prompt.md`, `quick.md`,
`start-here.md` (router + mid-size), `journal-state-plans.md` (SSOT honesty).
No new gate, no new module.

## Feature Registry Trace

Template self-change; template tests are acceptance. New tests: Tier-1
self-check + Tier-2 bundle floor, story issue_waived soft / empty-still-hard,
report follow-up off-tracker waiver / published-still-binds, kernel always
rendered, verification-independence Tier-1 wording, anchor module list
(active-only, none-when-empty), routing table, mid-size trap, SSOT collisions.

tier: 2
issue: #16
decisions: read the SP29 (tier scale) and SP19 (independence arithmetic)
designs as constraints; the Tier-1 self-check realignment refines SP29's
banding — recorded here, no separate ADR needed (a scale-banding correction,
not a new architecture decision).
product-goal: serves the framework's adopt-and-live-it promise; not
product-neutral.
review-waived: template-repo slice; independent fresh-context review runs before push (same session pattern as SP28-SP33)
