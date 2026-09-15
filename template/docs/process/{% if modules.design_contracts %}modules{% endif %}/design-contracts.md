# Module: design-contracts

**A surface's look is a contract, not taste.** UI work fails in a specific
way: every agent renders something plausible, nobody can say which picture
was *right*, and the same screen gets re-argued on every story. The cure is
the same one the code already uses for shared behaviour (mandatory rule 3):
declare the norm first, give every element a stable ID, pin it, and make
every change cite what it implements or amends. The design itself is judged
by a human and an independent reviewer against **rendered reference boards**,
never by a script — the script only guarantees that the norm exists, has not
moved silently, was accepted on a real GO, and is what the plan builds on.

On by default in the standard set; inert until the first registry entry exists.

## The objects

| Object | Where | Owner |
| ------ | ----- | ----- |
| **Contract** — the norm, one per surface, every element with a stable ID (screens S*, components C*, elevation E*, accessibility AX*, or the families you choose) | `docs/design/<surface>-contract.md` (`docs/process/design-contracts/templates/surface-contract.md`) | design work, amended before code |
| **Reference boards** — a numbered concept round rendered from the contract, mechanically QA'd, then **sealed** | `docs/design/concepts/<surface>-round-N/` (`docs/process/design-contracts/templates/round-README.md`) | the render kit; `scripts/process/seal.py` |
| **Independent review** — scored against a rubric written before scoring, with a `Decision: GO` line and the seal hash it applies to | `docs/design/concepts/<surface>-round-N-independent-review.md` (`docs/process/design-contracts/templates/independent-review.md`) | a reviewer independent of the authoring agent (`verification-independence.md`) |
| **Decision record** — makes the contract `accepted` and fixes the precedence order | `docs/process/adr/` | the owner |
| **Registry entry** — binds the four together and carries the pin | `docs/process/design-contracts/<surface>.json` | this gate |

## The registry entry

```json
{
  "surface": "web",
  "contract": "docs/design/web-contract.md",
  "status": "accepted",
  "pin": "sha256:<hex>",
  "id_prefixes": ["S", "C", "E", "AX"],
  "adr": "docs/process/adr/adr-0072-web-visual-language.md",
  "review": "docs/design/concepts/web-round-2-independent-review.md",
  "reference": "docs/design/concepts/web-round-2",
  "paths": ["frontend/src/**", "frontend/e2e/**"]
}
```

| field | required | meaning |
| ----- | -------- | ------- |
| `surface` | yes | slug, equals the filename stem |
| `contract` | yes | repo-relative path to the committed contract |
| `status` | yes | `draft` (being written, not yet the norm) or `accepted` |
| `pin` | yes | `sha256:<hex>` of the contract file (`sha256sum`), or an opaque marker |
| `id_prefixes` | yes | the ID families the contract defines; an ID is `<prefix><digits>[a-z]` |
| `adr` | accepted | the decision record that made it normative |
| `review` | accepted | the independent review carrying `Decision: GO` and the seal hash |
| `reference` | no | the sealed round folder the reviewer judges AFTER pictures against |
| `paths` | no | globs of the surface's code; a change there must cite an ID in its plan |
| `notes` | no | prose, ignored |

## Hard vs. best-effort (no false-green)

**Hard (CI fails):** invalid registry; a contract that is not a committed
file; a hash pin that no longer matches (the contract moved without a
re-pin); an ID defined by two headings; `accepted` without decision record,
without review, or with a review whose decision is not GO; a review naming a
different seal than the reference carries; a reference whose seal no longer
verifies (a board edited or added after the GO); an **active plan citing an
ID the contract does not define** — plausible-looking IDs are the failure
this module exists for.

**Best-effort (note, never fails CI):** an opaque pin; a `draft` contract;
reference boards rendered from an older contract (external drift: re-seal or
start a new round); a push touching the surface's `paths` while no active
plan cites an ID (DoR R5); an accepted contract without a sealed reference.

## Binding a plan to its contract

ID families are shared across surfaces — `E1` is an elevation on web and on
mobile — so a plan is judged only against the contract it **names**: the
contract's path anywhere in the plan, or a `design-contract: <surface>`
line. A plan that cites family IDs but names no contract gets one note; a
bound plan citing an ID its contract does not define is red. Zero-padding
is not identity: `C8` and `C08` are the same element. Keep labels that are
*not* contract IDs (finding numbers, brief items) out of the registered
families, or register only the families the contract really owns.

## Precedence — what wins when norms disagree

1. the functional contract (API, capability, behaviour spec)
2. the design contract
3. the sealed reference boards
4. the render kit's stylesheet and renderer
5. fine-tuning during implementation, each deviation recorded in the
   contract's amendment log with provenance (who, when, which issue)

A lower norm never silently overrides a higher one; the conflict is resolved
in the same piece of work and the loser is corrected.

## The lifecycle

```
draft contract ──▶ round N: render + mechanical QA ──▶ seal ──▶ independent review
      ▲                                                            │
      │   decisions & conditions written back, re-pinned;          │ GO
      └── boards changed? sub-revision N.1, re-seal, re-review ◀───┘
                                                                   ▼
                                  decision record: status accepted; registry points at the round
                                                                   ▼
        plan cites IDs (R5) ──▶ amend-before-code ──▶ tests/snapshots cite IDs ──▶ AFTER vs board (D8)
```

**Amend before code.** A change that needs a value the contract does not
carry, or a different one, writes the amendment (IDs, change, provenance)
into the contract *first*, re-pins, and only then implements. The pin makes
the order visible: a code diff that touches surface paths with an unchanged
pin implements the contract as it stands; a changed pin says the norm moved
and the amendment log says why.

## What stays project-specific

The **render kit** (how boards are produced), the **mechanical floor** it
enforces at export (hit areas, accessible names, overflow, contrast, focus
reachability — see the Surfaces section of `review-checklist.md` for the
floor itself), and the **token lints** (raw literals forbidden outside the
token owner, an allow-list of debt with a ceiling that may only fall) are
stack-bound and live in the project's own scripts. The module documents the
pattern; it does not ship the tools.

## Seal

```
python3 scripts/process/seal.py --seal docs/design/concepts/web-round-2 \
    --dep docs/design/web-contract.md --dep frontend/src/tokens.css
python3 scripts/process/seal.py --verify docs/design/concepts/web-round-2
```

`--seal` hashes every file in the folder plus the declared dependencies and
writes `manifest.json` + `manifest.sha256`. `--verify` exits 1 when the
folder is not what was sealed (edited, missing, or undeclared files) and 2
when only a declared dependency drifted. Quote the `manifest.sha256` value in
the review: that is what a GO applies to.

## Seed

An inert `surface.example.json` ships next to the templates; the gate skips
`*.example.json`. The gate is `scripts/process/check_design_contracts.py`.
