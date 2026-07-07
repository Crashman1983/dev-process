# SP33 — Gate hardening from the four-session hard audit

## Provenance

Four independent audit sessions (gate-breaker red-team / system coherence /
cold-start adopter / engineering economics; Opus + Sonnet + Fable) took the
process apart on 2026-07-07. This slice fixes every **reproduced gate defect**
(the flow/choreography and economics findings follow as SP34/SP35). Reports:
`.process-work/reviews/2026-07-07-audit-*.md`, campaign-bundled in GitHub
Issues.

## Fixes (each with the audit finding it closes)

1. **Tier range validation** (`check_review.py`) — the grammar accepted any
   integer tier; `tier=4` (nonexistent on the 0–3 scale) both skipped the
   `== 3` cross-model check and still cleared a Tier-3 plan via `>= tier`.
   A one-character edit defeated the gate's headline invariant. Fix: a tier
   outside 0–3 is malformed (hard); the cross-model check keys on `>= 3`
   defensively.
2. **Report header block ends at ANY heading** (`check_issues.py`) — the
   split on `"\n## "` let an `### `-first report treat the whole file as
   header, so a quoted `issue: #N` in the body counted as publication. Fix:
   split at the first ATX heading of any level.
3. **One fence-and-bullet discipline for every line grammar** — `~~~` fences
   were stripped by the issue/product-frame gates but not by review/telemetry
   (a `~~~`-quoted `verdict=pass` REALLY cleared a Tier-3 plan's presence);
   bulleted `- REVIEW`/`- GRADE` lines were invisible to both the parse and
   the malformed check (silent loss in the natural Markdown form). Fix:
   review + telemetry strip both fence markers (each closed by its own kind)
   and recognize records behind the shared `_LEAD` bullet/emphasis prefix.
4. **Decisions section parser stops at the next heading**
   (`check_decisions.py`) — an empty `## Type` followed by `## Intent`
   returned the next heading as the value, hard-failing with nonsense
   ("Type '## Intent' is not valid") while the documented soft path was
   unreachable. Fix: a following heading terminates the section (empty →
   soft, as documented).
5. **github-master fails clean on mixed-type `blocked_by`**
   (`check_github_master.py`) — `sorted([1, "STORY-0002"])` raised an
   uncaught TypeError (traceback), violating the file's own fail-clean
   comment. Fix: element-level string type-guard in `_load_snapshot`.
6. **Campaign parent identity is ref-normalized** (`check_issues.py`) —
   `#5` and `owner/repo#5` (the configured repo) are the same issue but were
   string-compared and reported as a "split campaign" (false-red). Fix:
   normalize via `parse_issue_ref` against the configured `github_repo`
   before comparing.
7. **Capability symbol match needs word boundaries**
   (`check_capability_contracts.py`) — bare substring matching let
   `symbols: ["get","p","3.0"]` pass against any spec by coincidence,
   satisfying the declared-first guarantee vacuously. Fix: word-boundary
   regex match (the architecture gate's existing posture).
8. **`code_roots` scalar is not iterated char-wise**
   (`check_architecture.py`) — `code_roots: src` (plausible YAML scalar)
   produced "code_root missing: s / r / c". Fix: hard-fail a non-list with a
   message naming the shape.
9. **Product-frame `status:` tolerates the `_LEAD` prefix**
   (`check_product_frame.py`) — a bulleted `- status: onboarded` read as
   "no status line" (inconsistent with every other grammar's tolerance).

## Non-goals

- Flow/choreography findings (plan-archival owner, hook-vs-baseline
  collision, tracker-less waivers, kernel merge, Tier-1/2 boundary wording,
  reviewer grammar in the prompt) — SP34.
- Economics findings (module-doc pointers, tier-partitioned reading, inbox
  in prime, routing table, mid-size-trap honesty) — SP35.
- The install-tag BLOCKER — resolved by tagging the release after merge
  (release-tag workflow), not by a template change; BOOTSTRAP skew warning
  goes to SP34.

## Anchor Delta

Six gate scripts touched (review, telemetry, issues, decisions,
github-master, capability-contracts, architecture, product-frame); no doc
semantics change, no schema change, no new artifact. Regression tests for
every fix.

## Feature Registry Trace

Template self-change; template tests are acceptance. New tests per fix:
tier-out-of-range malformed (grammar + presence not cleared), h3/h1/no-space
header bypass closed, `~~~`-fenced REVIEW/GRADE ignored (and the false-green
presence-clear case), bulleted REVIEW/GRADE parsed + linted, empty decision
section soft, mixed-type blocked_by fail-clean, same-issue campaign refs not
split, substring symbols rejected, scalar code_roots hard with message,
bulleted product-frame status accepted.

tier: 2
issue: #15
decisions: read the SP29 design (0-3 scale) and SP32 design (header-block
scoping) as constraints; no new or superseded record — these are defect
fixes inside decided designs.
product-goal: serves the framework's core promise (no false-greens); not
product-neutral.
