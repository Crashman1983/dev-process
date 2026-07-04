# Module: github-master

Opt-in. Inverts the source of truth: **GitHub Issues become the master**, and
the file registry becomes a mirror of them — *without* putting the network into
CI. Use this only when your backlog genuinely lives on GitHub. With this module
off (the default), the registry stays the source of truth and nothing here runs.

Depends on `feature-registry` (the mirror lives in the story files) and
`github-issues` (the issue refs are the join key).

## Two layers — never mix them

| Layer | What | Network | Where |
|---|---|---|---|
| **Sync** (`gh_sync.py`) | pull issues → the committed snapshot | yes | a tool + its own network-enabled job, never the gate job |
| **Gate** (`check_github_master.py`) | registry ↔ snapshot consistency, master invariants | **no** | offline, deterministic, over the committed snapshot |

Truth flows GitHub → snapshot → (checked against) registry. On divergence,
**GitHub wins** — re-run the sync and commit the refreshed snapshot. The snapshot
is the offline stand-in for GitHub truth, so the gate stays hermetic exactly like
every other gate in the process.

## The snapshot

`gh_sync.py` writes `.process-work/github-snapshot.json` (commit it):

```json
{
  "generated_by": "gh_sync",
  "issues": [
    {"number": 42, "story": "STORY-0001", "title": "…",
     "state": "open", "status": "in-progress",
     "blocked_by": null, "parent": null, "board_status": null}
  ]
}
```

- `story` is the join key — filled from each story's `issue` ref. An issue with
  no story yet is reported by the sync (and flagged by the gate) so you
  materialize a story for it.
- `state` is GitHub open/closed; `status` is the process status (from a
  `status:*` label, else derived).
- `blocked_by` / `parent` / `board_status` are **nullable slots**, each
  drift/consistency-checked when non-null (sequencing, sub-issues, the project
  board). `null` means "not yet mastered here" and the gate skips it.

## What the gate enforces (all offline)

- **Hard:** a malformed snapshot; a live (non-`deprecated`) story with no `issue`
  ref (the master requires every live story to trace to an issue); a story with
  no snapshot entry, or a snapshot entry with no story (the mirror must be
  complete both ways); **drift** where the registry disagrees with the snapshot
  on `title`, on `status` (both the value and its open/closed projection), or on
  a non-null `blocked_by` / `parent`.
- **Best-effort (note):** no snapshot yet — expected before the first sync.

Status↔state mapping the gate checks: `done` ⇒ issue **closed**;
`proposed`/`in-progress` ⇒ issue **open**; `deprecated` ⇒ either (and exempt
from the issue/snapshot invariants — retired work need not trace to a live
issue).

## Workflow

1. Create/modify the issue on GitHub (the master).
2. `python scripts/process/gh_sync.py` → refreshes the snapshot; materialize a
   story for any orphan issue it reports.
3. Commit the snapshot (and any new story). The gate then verifies, offline,
   that the mirror matches — in CI and locally.

## Project board

A GitHub Project board (Backlog → Ready → In-progress → Review → Done) is
supported the same two-layer way: `gh_board.py` (network) fills the snapshot's
`board_status`; the gate checks it offline. The one canonical mapping:

| board column | story `status` | issue `state` |
|---|---|---|
| Backlog, Ready | `proposed` | open |
| In-progress, Review | `in-progress` | open |
| Done | `done` | closed |

Columns match case-insensitively; `deprecated` stories are off the board
(exempt). The gate **hard-fails** an unknown column or a column whose implied
status disagrees with the story — so column, status, and issue state stay
mutually consistent, all offline. `gh_board.py <project-number> [--owner OWNER]`
reads the board into the snapshot; `--push` (an explicit extension point) moves a
card to the column its status implies. The move is a GitHub write — best-effort,
never a gate.

## The alternative

The registry-master default: leave this module off and author stories directly;
GitHub, if used at all, is then a projection (see the `github-issues` module),
not the master.
