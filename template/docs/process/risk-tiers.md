# Risk Tiers

Scope — not code volume — sets the tier. A change that another component, contract, persisted schema, or auth boundary **depends on** is Tier 2+ even with a tiny diff. Being merely user-*visible* is not itself Tier 2: a self-contained behavior change nothing else builds on (a new flag, a one-function fix) is Tier 1.

| Tier | Scope | Route |
|---|---|---|
| **Tier 0** | No behavior change (docs, formatting, comments), **or** a local, isolated, reversible change to a single file/function | No-behavior: commit directly (no plan/review cycle; the branching rules in `commits.md` still apply). Behavior: Quick flow — state goal + touched files + risk, then edit |
| **Tier 1** | Small, self-contained feature/fix: changes behavior but not a contract, persistence, auth, or another component. A new flag on an existing command, a bug fix in one function, a copy string with logic — user-*facing* but not user-*depended-upon* | Quick flow + a test |
| **Tier 2** | Changes behavior that another component, tool, or persisted state **depends on**: an interface/contract, a schema, a cross-component effect | Plan → execute → review before merge |
| **Tier 3** | Auth, persistence/migrations, security surface, or multi-repo contract | Plan + upfront design + review + (where configured) second-opinion review |

**Floor, not ceiling:** a label or convention may raise a tier; it never lowers the derived tier. Below the derived tier only with a one-line written justification.

**Recognizing your tier.** The categories above only help if you can see your task in them. Ask, of the concrete change:

- Does it **read or write persistence** (a database, a file, a durable store)?
- Does **untrusted or user-controlled input leave the process** — a redirect, rendered markup, a query, a subprocess, a file path?
- Does it touch **auth**, an **interface/contract** other code depends on, or **more than one surface**?
- Could it **lose or corrupt data**, or is it a **repeated change to the same owner** (see mandatory rule 4)?

A yes to any of these lifts the change to **Tier 2+ regardless of diff size** — a ten-line redirect that reads a stored URL is Tier 2, not Tier 0. When in doubt, tier up; the cost of an unneeded review is small next to the cost of an escaped defect.

**Verification scales too.** The tier sets not just *how much* review but *how independent* it must be (`verification-independence.md`): Tier 0 an in-context self-check; Tier 1–2 a fresh process reviewing a read-only bundle, not the producing context; Tier 3 additionally cross-model (where a second family is available) plus adversarial review. Production (plan, execute) runs in one warm context by design — independence is spent on verification, not manufactured during production.
