# <Surface> concept — round N

Rendered reference boards for `docs/design/<surface>-contract.md`. This
folder is **non-normative** (the contract is the norm) and, once sealed,
**immutable**: a further iteration becomes a new numbered round; a small
correction after review becomes a sub-revision (N.1, N.2) that edits in
place, re-seals, and is reviewed again under its new seal hash.

## Contents

| Path | What |
| ---- | ---- |
| `boards/` | one image per screen/state, named `<ID>-<viewport>-<theme>[-<state>].png` |
| `states.json` | the state list and element map the gate reads (below) |
| `states.js` / `cases.json` | the render kit's own matrix, if it has one |
| `export-report.json` | the render kit's QA output (hit areas, names, overflow, contrast) |
| `manifest.json`, `manifest.sha256` | the seal (`scripts/process/seal.py`) |

## states.json — state list and element map

The machine-readable side of the board matrix, written before the seal
(`docs/process/design-contracts/templates/states.example.json`):

- `viewports` (`id`, `width`, `height`), `themes` and `variants` (AX3, text
  size, …) are the round's axes; `surfaces` the platforms it draws.
- `views[].states[]` lists each rendered state with the viewports, themes,
  variants and `boards` it was rendered for — each a subset of the round's
  lists, each board a file in this folder. `views[].not_applicable` names a
  state the view does not have, with a reason.
- `elements` is the element map: every element once, with exactly one
  `owner` and an optional `role` (`main`, `secondary`); a view's `elements`
  names only elements the map has.
- `stories` lists the feature-registry stories the round covers, or
  `"n/a: <reason>"` — without the feature registry only the `n/a` form.
- Where the registry entry sets a `state_catalogue`, every catalogue state is
  in each view's `states` or `not_applicable`; other states are allowed.

Unknown keys are an error at every level, `_comment` is allowed at every
level. The file is required once a push touches the round: it sets or
changes the entry's `reference`, makes it `accepted`, changes its `review`
path, the seal, or the review file. A review file shared by several entries
touches every round it serves — one review file per round.

## Viewports and themes

| Viewport | Size | Themes |
| -------- | ---- | ------ |

## Board matrix

| Screen / component ID | States rendered | Missing (why) |
| --------------------- | --------------- | ------------- |

## Workflow of a round

1. Create `docs/design/concepts/<surface>-round-N/`; never edit a sealed round in place.
2. Decide contract and state coverage *before* rendering (the matrix above,
   written down as `states.json`).
3. Render deterministically with the kit; the export fails hard on the
   mechanical floor (touch target size, accessible names, overflow,
   contrast, focus reachability) — a failed export is not sealed.
4. Seal: `python3 scripts/process/seal.py --seal docs/design/concepts/<surface>-round-N --dep docs/design/<surface>-contract.md --dep <token files…>`.
   The seal covers every file in the folder: a `states.json` or a decision
   file added afterwards breaks it (`added after sealing`) — re-seal, and
   the round is reviewed again under the new seal hash.
5. Commission the independent review against the seal hash
   (`docs/process/design-contracts/templates/independent-review.md`).
6. Operator decisions (contract §9) and the review's conditions are written
   back into the contract with provenance, the contract is re-pinned in the
   registry, and — if the boards change — a sub-revision is rendered and
   re-sealed. A decision written into the contract changes it, so it needs
   a new pin; the contract is a `--dep` of the seal, so the reference then
   also notes drift until the round is re-sealed.
7. On GO: the decision record makes the contract `accepted`; the registry
   entry points at this folder as `reference`.

## Re-render

```
<the exact commands that reproduce boards/ from the kit>
```

## Evidence limits

What these boards do not show (real device, motion, screen reader, data
extremes) — so the reviewer does not claim it.
