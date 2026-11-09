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
| `status` | yes | `draft` (being written, not yet the norm), `accepted`, or `legacy` (a norm older than the registry: no ADR made it one and no GO exists — registered so plans can declare it; one note, no pin or ID notes, cited IDs still checked) |
| `pin` | yes | `sha256:<hex>` of the contract file (`sha256sum`), or an opaque marker |
| `id_prefixes` | yes | the ID families the contract defines; an ID is `<prefix><digits>[a-z]` |
| `adr` | accepted | the decision record that made it normative |
| `review` | accepted | the independent review carrying `Decision: GO` and the seal hash |
| `reference` | no | the sealed round folder the reviewer judges AFTER pictures against |
| `paths` | no | globs of the surface's code; a change there must cite an ID in its plan |
| `notes` | no | prose; amendments go into `<surface>.notes.md` next to the entry, whole lines appended (`merge=union`), read with `notes` — a note citing an older seal must say it is historical |
| `state_catalogue` | no | the states every view of the round renders or names as not applicable: a list, or a repo path to a JSON list — one place for every surface |
| `defaults`, `extra_axes`, `rule_sources` | no | read by the ui-check gate (below) |
| `_comment` | no | prose; any other key is a note (a typo of a known field?) |

## Hard vs. best-effort (no false-green)

**Hard (CI fails):** invalid registry; a contract that is not a committed
file; a hash pin that no longer matches (the contract moved without a
re-pin); an ID defined by two headings; `accepted` without decision record,
without review, or with a review whose decision is not GO (the template's
unfilled `GO | GO with conditions | NO GO` is no decision); a review naming a
different seal than the reference carries; a reference whose seal no longer
verifies (a board edited or added after the GO); an **active plan citing an
ID the contract does not define** — plausible-looking IDs are the failure
this module exists for (an ID that only a `DECISION` line quotes is not
defined); a malformed `state_catalogue` or `states.json`; an owner decision
ID a round holds twice with different text; an acceptance item that lost its
coverage against the fork point; and, for a round the push touches, a
missing `states.json` and the checks against the world around the round —
the catalogue, the registry's stories, a GO that leaves a visible item
uncovered (below).

**Best-effort (note, never fails CI):** an opaque pin; a `draft` contract; a `legacy` norm (one note);
reference boards rendered from an older contract (external drift: re-seal or
start a new round); a push touching the surface's `paths` while no active
plan cites an ID (DoR R5); an accepted contract without a sealed reference;
an unknown key in a registry entry; the same round checks for a round no
push touches; no fork point to tell whether a push touches a round; a story
of the round with no visible item; an owner decision on a retired item or a
deleted story; an unbound decision in the coverage form in a contract.

## The round's state list and element map

A round says in `states.json` what its boards cover: views × states ×
viewports × themes, plus `variants` (AX3, text size) and the `surfaces` it
draws, and which owner each element of a view has. The format, with an
example, is in `docs/process/design-contracts/templates/round-README.md` and
`docs/process/design-contracts/templates/states.example.json`; this gate is the
one owner of reading it. What the file says about itself — its keys at every
level, each state's axes within the round's lists, the
boards it names, every element once with an owner, `stories` as a non-empty
list or `n/a: <reason>` — is checked always.

**A round is judged hard where a push touches it.** Against the fork point
(`check_review.merge_base`), an entry's round is touched when the push sets
or changes its `reference`, makes it `accepted`, changes its `review` path,
changes the seal (`manifest.sha256`, compared by blob ID; missing at the fork
point counts as changed — a sub-revision N.1 touches the round), changes the
review file (a new GO section), or adds the entry file (a `legacy` entry's
round is not judged). For a touched round:

- `states.json` is required;
- every state of the catalogue — the union of every entry on the round, as
  it stands now and at the fork point, so a push cannot drop a state for its
  own GO — is in each view's `states` or `not_applicable`;
- with the feature registry, `stories` is required: each a story of the
  registry, at least one acceptance item visible to the round among them,
  the round's `surfaces` within the registry's `surfaces`; without the
  registry a list is red (no coverage could be judged) and `n/a: <reason>`
  is the form;
- an accepted entry whose review says GO needs every visible item covered
  (below), and an owner decision may not name an item that never was one.

A round no push touches gets the same findings as notes: a story deleted, a
state added to the catalogue elsewhere must not red every push until the
round is re-sealed and re-reviewed. The rule hangs on the touch only, never
on what the fork point holds. Without a fork point (main CI, a shallow clone,
a criss-cross) one note names the reason — never everything touched, never
a silent pass. Rounds accepted before this rule stay a note until a push
touches them.

**One review file per round.** A changed review file touches every round
whose entry names it, so a new section for one surface makes the shared
round's `states.json` due. Entries on *different* rounds that share a review
file couple those rounds: red when the push touches one of them, a note
otherwise.

**The seal.** It covers every file of the folder: a `states.json` or a
decision file added to a sealed round breaks it (`added after sealing`) —
re-seal, and the round is reviewed again under the new hash. A decision
written into the contract changes the contract: it needs a new pin, and
since the contract is a `--dep` of the seal, the reference notes drift too.

**Owner decisions with an ID.** An owner decision that changes or drops
acceptance items carries an ID: `DECISION <date> owner <ID>: change|drop
<Story>#AC<n>[, …] — <reason>` in the round folder or the review; in the
contract (§9) it names its round, `owner <round>/<ID>`, and counts for that
round only.

- `<ID>` is like `D7`, `D-7` or `F1` (`[A-Z][A-Z0-9]*-?\d+`); zero-padding is
  no new ID (`D07` is `D7`), a dash is (`D-7` is not `D7`).
- `<round>` is the round's folder name, the token split at its last `/`
  (`owner a/web-round-2/D7` is round `web-round-2`'s).
- Read unfenced from the round folder's `*.md`, the review and the contract
  of every entry on the round. In the folder and the review an unbound
  decision is the round's; a bound one counts only for the round it names,
  wherever it stands. In a contract only the bound form counts — an unbound
  one in the coverage form covers nothing and gets a note to bind it; other
  owner questions in §9 are left alone. So a decision of an older round
  neither covers the new one nor collides with its IDs.
- One ID, one decision per round: the same ID again is a quote and must say
  the same (whitespace, emphasis and list markers aside); with other text it
  is red. A decision without an ID, not the owner's, inside a fence or
  without ` — <reason>` covers nothing.
- An item the decision names must have existed: one that never was in the
  story's `acceptance` or `retired` is red where the push touches the round.
  A retired id or a deleted story is a note — a sealed round stays green after
  "drop, then retire"; an item gone without `retired` gets a note that says so.

## Coverage — computed, and a GO only with all of it

Which acceptance items a round covers is computed, not copied into the
review. An item of a story in the round's `stories` is **visible** to the
round when it is not `owned_by` a shared proof layer and its surfaces (the
item's, else the story's, else the project's) meet the round's `surfaces` —
without `surfaces` every item counts, the implicit surface always does. It is
**covered** by a feature-registry `design` anchor into the round
(`<round>/<view>#<state>`, a view and a state its `states.json` renders —
the registry gate checks the anchor) or by an owner decision with an ID that
changes or drops it. An anchor counts for the round it names, so a new round
does not red the anchors of the old one.

```
python3 scripts/process/check_design_contracts.py . --coverage <surface>
```

prints the table of the surface's reference round — each visible item, the
anchor or decision that covers it (or **uncovered**), and the viewports,
themes and variants of the anchored state. The review bundle shows the same
table; the review file does not copy it.

- **The gate:** an `accepted` entry whose review says GO, on a round with a
  visible item uncovered, is red naming every such item where the push
  touches the round — a newly accepted round always is — and a note
  otherwise.
- **Lost coverage** is a delta rule, not a touch: an item that stands and is
  visible to the round at the fork point and now, was covered there (an
  anchor, or a decision of an entry that referenced the round there) and is
  not now, is red — the message names the item: it lost its coverage. A
  removed anchor, a dropped bound decision, a changed `contract` path or a
  `reference` moved out of a shared round all show. Deleted stories and
  items and retired ids do not count, and the rule leaves every other note a
  note. A contract the fork point's entry names that cannot be read there
  counts as changed (fail-closed). Without a registry at the fork point the
  anchors are not compared (a note); the decisions still are.

## Binding a plan to its contract

ID families are shared across surfaces — `E1` is an elevation on web and on
mobile — so a plan is judged only against the contract it **names**: the
contract's path anywhere in the plan, or a `design-contract: <surface>`
line. A plan that cites family IDs but names no contract gets one note; a
bound plan citing an ID its contract does not define is red. Zero-padding
is not identity: `C8` and `C08` are the same element. Keep labels that are
*not* contract IDs (finding numbers, brief items) out of the registered
families, or register only the families the contract really owns.

## Declaring the contract

Optional, per project. A project that wants every visual change to name its
norm writes `docs/process/design-contract-declaration.local.json`:
`{"from": "YYYY-MM-DD", "spec_above": N}`. From then on every active Tier 2+
plan states `design-contract: <surface> | n/a — <reason>`, and a declared
contract carries a non-empty `## Design Contract Trace` (the contract
sections, screen IDs and briefs the work follows, and every deviation).
Naming the contract's path still binds the plan to its contract, but no
longer satisfies the declaration. Red: no line,
an unregistered surface, `n/a` without a reason, a missing or empty trace.

- **Which plans:** a plan under `.process-work/plans/` whose first commit is
  on or after `from` (the author day — a backdated file name proves nothing;
  an uncommitted plan is bound), and a Spec Kit plan numbered above
  `spec_above` (all of them without it). Older plans get one summary note.
  In a shallow clone a plan whose first commit lies beyond the clone's
  history has no known age: a note names it and `git fetch --unshallow`,
  never a refusal; a full clone judges it.
- **Read at the fork point**, like the review evidence rules: a branch
  cannot lift the duty for itself. The file lives beside the registry
  folder, not in it — it is no surface.
- Without the file nothing changes. Whether the trace matches the contract
  is the review's call, never the gate's.

## UI check — considered, not judged

The `ui-check` gate (`scripts/process/check_ui.py`, every project, starts
observing) asks a plan whose branch touches UI how the UI was considered:
one `ui-check:` block with an answer per axis (`/plan`). This module feeds it:

- a registry's `paths` count as UI, beside `areas.ui` in `testing.local.json`;
- a plan that declares a contract owes the block, and one block per surface
  where it declares several (`ui-check <surface>:`);
- `defaults` (axis → value) lets a plan answer `inherited` on that axis —
  the surface's standing answer, e.g. its viewports;
- `extra_axes` adds the project's own axes;
- `rule_sources` names the project's UI rule files: `rules` must cite one of
  them, and `rules: n/a` is a finding.

A green gate is no design verdict: it proves the questions were answered,
not the answers. The reviewer judges them against the board.

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

## Probe build — a completeness check before the freeze

A design package can look complete and still leave an implementer guessing.
Before a round is frozen, an optional **probe build** finds out cheaply: a
low-cost implementer builds one surface from the package alone — boards,
contract, the stories' acceptance items — with no other context and no
questions. Every place where it had to improvise (an element no board
places, a state no board draws, a value no contract carries) is recorded as
a gap in the package and closed, or decided by the owner, before the freeze.
The probe's code is thrown away; only the list of gaps counts.

Downstream, three implementers built the same surface from one package and
all three improvised in exactly the same places — the places the boards were
silent. A probe build would have found those gaps before any of the three
started.

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
`*.example.json`. `docs/process/design-contracts/templates/states.example.json`
is the seed of a round's `states.json`. The gate is `scripts/process/check_design_contracts.py`.
