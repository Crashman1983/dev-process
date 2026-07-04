# SP22 — github-master spine (invert the SSOT direction, keep gates hermetic)

## Problem / decision

For projects that run their backlog on GitHub, the user wants **GitHub Issues
(with sub-issues and a project board) to be the master** — the single source of
truth — not the file registry. But every gate SP18–21 built is **hermetic**: it
runs offline over files, no network, so CI is deterministic and cannot be wedged
by auth/rate-limits/"deleted-vs-invisible". Naively fetching truth from GitHub in
a gate throws that away.

SP22 resolves this as an **opt-in `github_master` adapter** that inverts the
direction of truth *without* putting the network into hard checks, by separating
two layers:

| Layer | Does | Network | Where |
|---|---|---|---|
| **Sync** (writes/reads GitHub) | pull issues → a committed snapshot; (later) push board moves | yes | a tool + its own CI job, never the gate job |
| **Gate** (checks) | registry ↔ snapshot consistency; master invariants | **no** | offline, over the committed snapshot |

GitHub is master: truth flows GitHub → snapshot → (compared against) registry.
On divergence, GitHub wins and you re-sync. The **snapshot is the offline
stand-in for GitHub truth**; the gate is fully deterministic over it. The
portable **registry-master default is untouched** — `github_master` is off by
default, and with it off nothing in SP18–21 changes.

## The snapshot

`.process-work/github-snapshot.json`, written by the sync tool, committed:

```json
{
  "generated_by": "sync",
  "issues": [
    {"number": 42, "story": "STORY-0001", "title": "…",
     "state": "open", "status": "in-progress",
     "blocked_by": ["STORY-0002"], "parent": null, "board_status": null}
  ]
}
```

- `story` is the join key to the registry (the story's `issue` ref identifies
  which issue; sync fills `story` from that mapping).
- `state` = GitHub open/closed. `status` = the process status (from labels /
  board — SP24 fills `board_status`). `parent` (SP23) and `board_status` (SP24)
  ship as nullable slots now so later slices only *fill* them, never reshape.

The registry files stay the working representation and carry a
`"source": "github"` marker in `github_master` mode (they mirror the master; on
conflict, re-sync from GitHub — do not hand-edit the mirrored fields).

## The gate — `check_github_master.py` (module: `github_master`)

Runs only when the module is on. Everything it hard-fails is offline and
deterministic (registry files + committed snapshot):

**Hard (CI fails):**
- Malformed snapshot (invalid JSON, not the schema, non-UTF-8).
- A non-`deprecated` story with **no `issue` ref** — in github-master mode every
  live story must trace to an issue (the master requires it). This is the
  invariant that makes "issues are master" real and is fully offline.
- A story whose `issue` has **no matching snapshot entry** (`story` join) — the
  mirror is stale or the story is phantom; re-sync.
- **Drift:** a story field that disagrees with its snapshot entry on
  `title`, `status`↔`state`, and (slots) `blocked_by` — GitHub is master, the
  registry may not silently diverge. Status↔state mapping is documented
  (`done`→closed; `proposed|in-progress`→open; `deprecated`→either).
- A snapshot entry whose `story` matches no registry file (an issue pulled but
  never materialized) — hard, so the mirror is complete.

**Best-effort (advisory note, never CI):**
- No snapshot file yet (pre-sync) — expected before the first sync.
- Freshness of the snapshot vs *live* GitHub — that comparison needs the
  network and lives in the **sync tool**, not the gate.

## The sync tool — `gh_sync.py` (best-effort, network, not a gate)

Pulls issues via `gh` → writes the snapshot (and, in github-master mode,
materializes/updates the registry mirror). Thin, `gh`-dependent, best-effort —
the same posture as `new_issue.sh`. Not unit-tested against live GitHub; the
**gate** (offline, over a crafted snapshot) is the tested core. Runs in its own
network-enabled CI job or locally, never in the hermetic gate job.

## What SP22 deliberately does NOT do

- Sub-issues / `parent` truth (SP23) — the snapshot carries a nullable `parent`
  slot only.
- Board column truth + automation (SP24) — nullable `board_status` slot only.
- Lossy full-generation of acceptance/tests from issue bodies — the registry
  still authors those; the master owns title/status/relationships/existence.

## Alternatives considered

- **Gate fetches live GitHub:** rejected — network in hard checks, non-hermetic,
  flaky, defeats the whole SP18–21 posture.
- **Drop file-registry, GitHub-only:** rejected — kills portability for
  non-GitHub adopters and still needs the snapshot trick for hermetic CI.
- **Registry stays master, GitHub a projection:** the SP21 default — kept as the
  default, but it is *not* what github-master mode is; the user wants issues as
  master for GitHub projects, and this adapter delivers that.

## Anchor Delta

New opt-in `github_master` module (depends conceptually on `github_issues` +
`feature_registry`): `check_github_master.py` gate, `gh_sync.py` tool, a module
doc, snapshot schema, gate-runner wiring, copier answer. No core rule change; the
registry-master default and every existing gate are untouched when the module is
off.

## Feature Registry Trace

Process-template self-change; template tests are acceptance. New
`test_github_master.py`: module on/off wiring; snapshot schema hard; missing-
issue invariant hard; story↔snapshot join (both directions) hard; drift on
title/status/blocked_by hard; status↔state mapping; pre-sync soft; neutrality;
default-untouched (github_master off ⇒ no new enforcement).
