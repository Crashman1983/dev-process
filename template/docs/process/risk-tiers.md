# Risk Tiers

Scope — not code volume — sets the tier. A change that another component, contract, persisted schema, or auth boundary **depends on** is Tier 2+ even with a tiny diff. Being merely user-*visible* is not itself Tier 2: a self-contained behavior change nothing else builds on (a new flag, a one-function fix) is Tier 1.

| Tier | Scope | Route |
|---|---|---|
| **Tier 0** | No behavior change (docs, formatting, comments), **or** a local, isolated, reversible change to a single file/function | No-behavior: commit directly (no plan/review cycle; the branching rules in `commits.md` still apply). Behavior: Quick flow — state goal + touched files + risk, then edit |
| **Tier 1** | Small, self-contained feature/fix: changes behavior but not a contract, persistence, auth, or another component. A new flag on an existing command, a bug fix in one function, a copy string with logic — user-*facing* but not user-*depended-upon* | Quick flow + a test |
| **Tier 2** | Changes behavior that another component, tool, or persisted state **depends on**: an interface/contract, a schema, a cross-component effect | Plan → execute → review before merge |
| **Tier 3** | Auth, persistence/migrations, security surface, or multi-repo contract | Plan + upfront design + review + (where configured) second-opinion review |

**Floor, not ceiling:** a label or convention may raise a tier; it never lowers the derived tier. Below the derived tier only with a one-line written justification.

**The tier attaches to the change, not to the effort's title.** A slice that merges in stages carries a tier *per stage*: a behaviour-neutral extraction stage whose proof is mechanical (a protected test set unchanged and green on every commit) derives Tier 2 — fresh bundle review, no cross-model/adversarial program — even when the slice's behaviour-changing stage is Tier 3. Paying the Tier 3 ritual twice because both stages share a heading is spend without risk behind it; the stage that changes behaviour pays it once. The one-line justification duty above covers the split: the stage plan names its own tier and why.

**Recognizing your tier.** The categories above only help if you can see your task in them. Ask, of the concrete change:

- Does it **read or write persistence** (a database, a file, a durable store)?
- Does **untrusted or user-controlled input leave the process** — a redirect, rendered markup, a query, a subprocess, a file path?
- Does it touch **auth**, an **interface/contract** other code depends on, or **more than one surface**?
- Could it **lose or corrupt data**, or is it a **repeated change to the same owner** (see mandatory rule 4)?

A yes to any of these lifts the change to **Tier 2+ regardless of diff size** — a ten-line redirect that reads a stored URL is Tier 2, not Tier 0. When in doubt, answer these questions for the concrete change: a yes lifts it, a no keeps it where its scope puts it. Size and importance are no reasons to tier up — a large change is split, not promoted; an unneeded Tier 3 costs a cross-model review, a refute and every round after them, and downstream that cost, not escaped defects, became the bottleneck.

**Verification scales too.** The tier sets not just *how much* review but *how independent* it must be (`verification-independence.md`): Tier 0–1 an in-context self-check; Tier 2 a fresh process reviewing a read-only bundle, not the producing context; Tier 3 additionally cross-model (where a second family is available) plus adversarial review. How hard the change is attacked — a refute, a fresh agent that tries to break it — scales with it too; `refute.md` owns that table. Production (plan, execute) needs no independence — warm in an interactive session, handed over through the committed plan by the dispatch chain (`verification-independence.md`, "Production needs no independence"); independence is spent on verification.

## Template updates

A pure template update uses computed provenance instead of another review of
released template code. `uv run --script scripts/process/template_verify.py --base <integration-base>`
re-renders both pinned releases with the recorded answers. It compares the
old project files too: deleting a local duty during an update is project delta,
even when the result is identical to the new release.

- **Pure update:** gates and project tests must pass; no REVIEW is needed for
  release-identical files. Mark its plan `template-update: true`. This is an
  opt-in to verification, not a waiver; the gate recomputes the evidence.
- **Project delta:** one independent Tier 2 reviewer covers that delta, with
  a digest-bound REVIEW of the update range; no panel. Local files, owned
  files, hooks, Makefiles, deleted or edited tests and conflict resolutions
  stay project work. Answer changes stay project delta too.
- **Enforcement migration:** the project's own change to gate code or its
  configuration stays Tier 3 — a gate file that differs from the release
  (helpers can change enforcement transitively, so anything in
  `scripts/process/` counts). Gate code exactly as released is no
  migration: the release was reviewed and refuted upstream, and the
  acknowledgment covers its behavior notes (downstream, every release made
  every update a Tier 3 review of code no project line had touched).

The owner or steward acknowledges the release behavior notes with
`uv run --script scripts/process/template_verify.py --base <integration-base> --ack <owner>`; commit
the generated acknowledgment. This attests a decision, not file coverage.
A missing render, changed source, mutable HEAD pin or mismatched file cannot
use the exemption. `releases.md` gives the update sequence.
