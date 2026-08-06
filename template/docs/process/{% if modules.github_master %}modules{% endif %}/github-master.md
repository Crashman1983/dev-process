# Module: github-master

Opt-in. Makes explicit what the lean process assumes anyway: **GitHub Issues
are the work log's source of truth** (what is proposed, in flight, done) —
*without* putting the network into CI. The separate question "what can the
product do today, and where is that proven?" belongs to the feature inventory
(`feature-registry` module) and is deliberately not coupled here.

Depends on `github-issues` (labels, EARS templates, issue hygiene).

## Two layers — never mix them

| Layer | What | Network | Where |
|---|---|---|---|
| **Sync** (`gh_sync.py`) | pull issues → the committed snapshot | yes | a tool you run (or wire into a network job); never the gate job |
| **Gate** (`check_github_master.py`) | snapshot well-formedness + internal consistency (DoR at rest, board vs state/status) | **no** | offline, deterministic, over the committed snapshot |

Truth flows GitHub → snapshot. The snapshot is the offline stand-in for GitHub
truth, so the gate stays hermetic exactly like every other gate in the process.

## Staleness — the one caveat that matters

The gate is deterministic over the *committed* snapshot and has **no network and
no clock**, so it **cannot detect a stale snapshot**: a snapshot that lags
GitHub passes green. "GitHub is master" therefore means *master as of the last
`gh_sync` you ran and committed* — nothing forces or verifies freshness. The
gate surfaces this every run as a note showing the snapshot's `generated_at`;
keeping the mirror fresh is your discipline. No sync CI job ships (it needs
GitHub auth + `project` scope); wiring one is an adopter recipe.

## The snapshot

`gh_sync.py` writes `.process-work/github-snapshot.json` (commit it):

```json
{
  "generated_by": "gh_sync",
  "generated_at": "2026-08-06T12:00:00Z",
  "issues": [
    {"number": 42, "title": "…",
     "state": "open", "status": "in-progress",
     "board_status": null,
     "dor": {"typed": true, "ears": true, "deviation": false}}
  ]
}
```

- Entries are keyed by issue `number` — issues are the work log; there is no
  file mirror to join against.
- `state` is GitHub open/closed; `status` is the process status (from a
  `status:*` label, else derived).
- `board_status` is a **nullable slot**, consistency-checked *when non-null*
  (`gh_board.py` fills it); `null` ⇒ the gate skips it. The gate is honest
  either way — it never invents a value.

## What the gate enforces (all offline)

- **Hard:** a malformed snapshot (unknown keys, missing/duplicate `number`,
  bad `state`, malformed `dor`); an **in-progress issue that is not Ready**
  (see below); a **board column inconsistent** with the issue's state or its
  `status:*` label.
- **Best-effort (note):** no snapshot yet — expected before the first sync; a
  snapshot entry predating the `dor` slot (re-sync to enforce the DoR).

**Definition of Ready, enforced.** `gh_sync.py` is the one place that sees the
live issue, so it derives the DoR facts there and stores them in the entry's
`dor` slot: `typed` (a `type:*` label — R1), `ears` (an EARS acceptance section,
heading or `shall` clause, case-insensitive; an epic is exempt — R2), and
`deviation` (the body records a `## Deviations` note — the DoR's named escape,
`definition-of-ready-and-done.md`). The gate then enforces, offline: an open
issue at `in-progress` (work has started) that is neither Ready nor carries a
deviation **fails hard** — the DoR moves from checklist to gate. `done` is the
review gate's business. The body itself is never snapshotted, only the derived
booleans.

## Workflow

1. Create/modify the issue on GitHub (the master).
2. `python scripts/process/gh_sync.py` → refreshes the snapshot.
3. Commit the snapshot. The gate then verifies it, offline — in CI and locally.

## Project board

A GitHub Project board (Backlog → Ready → In-progress → Review → Done) is
supported the same two-layer way: `gh_board.py` (network) fills the snapshot's
`board_status`; the gate checks it offline. The one canonical mapping:

| board column | `status` label | issue `state` |
|---|---|---|
| Backlog, Ready | `proposed` | open |
| In-progress, Review | `in-progress` | open |
| Done | `done` | closed |

Columns match case-insensitively. The gate **hard-fails** an unknown column, a
column whose implied state disagrees with the issue (a closed issue parked in
In-progress), or one whose implied status disagrees with the `status:*` label —
so column, label, and state stay mutually consistent, all offline.
`gh_board.py <project-number> [--owner OWNER]` only *reads* the board into the
snapshot — moving cards stays a manual (or GitHub-project-automation) act. Note
the asymmetry: the `status:*` **label** is what `gh_sync.py` derives status
from — the board column is a checked *view* of that status, never a second
writer.

## The alternative

Leave this module off: issues (if used at all — `github-issues` module) are
then convention without the snapshot gate, and the DoR is carried by review
judgment alone.
