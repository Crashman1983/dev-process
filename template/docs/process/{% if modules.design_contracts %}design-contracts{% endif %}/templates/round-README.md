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
| `states.js` / `cases.json` | the state × viewport matrix the boards were rendered from |
| `export-report.json` | the render kit's QA output (hit areas, names, overflow, contrast) |
| `manifest.json`, `manifest.sha256` | the seal (`scripts/process/seal.py`) |

## Viewports and themes

| Viewport | Size | Themes |
| -------- | ---- | ------ |

## Board matrix

| Screen / component ID | States rendered | Missing (why) |
| --------------------- | --------------- | ------------- |

## Workflow of a round

1. Create `docs/design/concepts/<surface>-round-N/`; never edit a sealed round in place.
2. Decide contract and state coverage *before* rendering (the matrix above).
3. Render deterministically with the kit; the export fails hard on the
   mechanical floor (touch target size, accessible names, overflow,
   contrast, focus reachability) — a failed export is not sealed.
4. Seal: `python3 scripts/process/seal.py --seal docs/design/concepts/<surface>-round-N --dep docs/design/<surface>-contract.md --dep <token files…>`
5. Commission the independent review against the seal hash
   (`docs/process/design-contracts/templates/independent-review.md`).
6. Operator decisions (contract §9) and the review's conditions are written
   back into the contract with provenance, the contract is re-pinned in the
   registry, and — if the boards change — a sub-revision is rendered and
   re-sealed.
7. On GO: the decision record makes the contract `accepted`; the registry
   entry points at this folder as `reference`.

## Re-render

```
<the exact commands that reproduce boards/ from the kit>
```

## Evidence limits

What these boards do not show (real device, motion, screen reader, data
extremes) — so the reviewer does not claim it.
