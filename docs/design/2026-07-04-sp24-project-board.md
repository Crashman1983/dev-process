# SP24 — Project board (status field + hermetic consistency gate + automation)

## Problem / decision

Under `github_master`, the user wants a **GitHub Project board**
(Backlog → Ready → In-progress → Review → Done) that is both **automated**
(cards added and moved for them) and **gated** (kept consistent). These two
wants sit on opposite sides of the hermeticity line SP22 drew, so SP24 keeps
them on their own layers:

- **Gate (hermetic, offline):** the board column recorded in the snapshot must
  be consistent with the story's status (and, transitively, the issue state).
  No network. This is the "gated" half.
- **Automation (network, best-effort):** `gh_board.py` reads the board into the
  snapshot's `board_status` slot and can push a card to the column its status
  implies. This is the "automated" half — a tool + its own network job, never
  the gate.

The SP22 snapshot already carries a nullable `board_status` slot, so SP24 only
*fills* and *checks* it — no schema reshape.

## The board ↔ status mapping (the one canonical table)

| board column | story `status` | issue `state` |
|---|---|---|
| Backlog, Ready | `proposed` | open |
| In-progress, Review | `in-progress` | open |
| Done | `done` | closed |

Columns are matched case-insensitively. `Backlog`/`Ready` both mean not-yet-
started (`proposed`); `In-progress`/`Review` are both active (`in-progress` —
the registry has no separate `review` status, and inventing one is out of
scope); `Done` is `done`. `deprecated` stories are exempt (retired, off the
board).

## The gate — extends `check_github_master.py`

For each story whose snapshot `board_status` is non-null:
- **Hard:** an **unknown board column** (not in the table) — the board can't be
  validated against a column the process doesn't understand.
- **Hard:** the column's implied status ≠ the story's status (e.g. a card in
  `Done` while the story is `in-progress`). Combined with the SP22 status↔state
  check, this makes column, status, and issue-state mutually consistent, all
  offline.
- `null` `board_status` ⇒ skip (not yet synced) — same convention as the other
  slots.

No new gate; the board check joins the existing github-master drift loop (one
owner for "registry ↔ snapshot consistency").

## The automation — `gh_board.py` (network, best-effort, not a gate)

- **Read (default):** `gh project item-list …` → for each issue on the board,
  read its Status field and write `board_status` into the committed snapshot.
  Then the gate verifies consistency offline.
- **Push (`--push`):** for a story whose board column disagrees with its status,
  move the card to the column its status implies (a GitHub write). Opt-in,
  best-effort, needs the `project` scope.

Thin, `gh`-dependent, not unit-tested against a live board — the same posture as
`gh_sync.py`. The tested, hermetic contract is the gate.

## Alternatives considered

- **Gate reads the board live:** rejected — network in a hard check, the whole
  thing SP22 exists to avoid.
- **A `review` story status to match the Review column:** rejected — it would
  ripple through every status-consuming gate for one board column; mapping
  Review→`in-progress` is lossless enough and keeps the status enum stable.
- **Board automation as a gate:** rejected — moving cards is a network write;
  it can't be hermetic, so it stays a tool.

## Anchor Delta

`check_github_master.py` gains the board-column consistency check; a new
`gh_board.py` tool; the github-master doc documents the mapping and the two
layers. No core rule change, no schema reshape (the slot already exists).

## Feature Registry Trace

Template self-change; template tests are acceptance. Extended
`test_github_master.py`: board_status null-skip; unknown-column hard; column↔
status mismatch hard (each column); consistent case OK; deprecated exempt.
Tool presence on/off; neutrality.
