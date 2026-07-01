# Risk Tiers

Scope — not code volume — sets the tier. User-visible, cross-component, API/interface, auth, or persistence changes are Tier 3+ even with a tiny diff.

| Tier | Scope | Route |
|---|---|---|
| **Tier 0** | No behavior change (docs, formatting, comments) | Direct commit |
| **Tier 1** | Local, isolated, reversible; single file/function | Quick flow: state goal + touched files + risk, then edit |
| **Tier 2** | Small feature/fix, no contract/persistence/auth impact | Quick flow + a test |
| **Tier 3** | User-visible, cross-component, or touches an interface/contract | Plan → execute → review before merge |
| **Tier 4** | Auth, persistence/migrations, security surface, or multi-repo contract | Plan + upfront design + review + (where configured) second-opinion review |

**Floor, not ceiling:** a label or convention may raise a tier; it never lowers the derived tier. Below the derived tier only with a one-line written justification.
