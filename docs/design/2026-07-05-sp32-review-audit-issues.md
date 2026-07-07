# SP32 — Audits and reviews visible in GitHub Issues

## Problem

Independent reviews and audits produce the process's most valuable negative
knowledge — findings — and today that knowledge is the least visible artifact
in the flow. The `REVIEW` journal line is a one-line attestation (by design);
the full review — the prompt it ran with, the verdict, each finding and what
happened to it — lives in chat history or nowhere. Consequences:

- Findings that deserve follow-up are not tracked work; they survive only if
  someone remembers to file an issue (the discovered-work inbox catches
  mid-flow observations, but nothing binds *review findings* to issues).
- A multi-report campaign (like the six-persona audit that produced SP28) has
  no bundled, linkable record — the synthesis lived in a design doc, the
  per-persona reports nowhere.
- For a team on GitHub, "what did the last audit find and what happened to
  it?" is unanswerable from the repo.

User requirement: audits and reviews — **prompt, result, and follow-up
measures (findings)** — become visible in GitHub Issues, **bundled when they
belong to a campaign**.

## Decision

Three layers, matching the corpus's established posture (network in tools,
never in gates; structured line grammar + hermetic lint; prose duty where only
judgment can decide):

### 1. Report artifact — `.process-work/reviews/YYYY-MM-DD-<slug>.md`

Reviews and audits get a durable report file beside plans (same working-memory
root, same lifecycle: kept while relevant, archivable). Machine-readable
header lines + free sections:

```
review: sp31-product-frame        (or  audit: qa-persona)
work: #42                         (issue ref or plan slug it reviewed)
tier: 2                           (omit for tier-less audits)
campaign: 2026-07-round-1         (optional — bundles reports)
issue: #57                        (the published issue; or publish-waived: <reason>)
campaign-issue: #50               (required when campaign: is set and published)

## Prompt      — the verbatim prompt the reviewer/auditor ran with
## Result      — verdict + summary
## Findings    — one FINDING line per finding + free prose
```

Findings use a structured grammar (the `REVIEW`/`GRADE` house pattern):

```
FINDING sev=blocker|major|minor|nit action=fix|accept|follow-up issue=#N|- <title>
```

`action=fix` = fixed within the reviewed change; `accept` = consciously
accepted, reason in prose; `follow-up` = becomes tracked work — **must** carry
an issue ref. Fenced examples are quotations and ignored (house rule).

### 1b. Discovered work keeps the form and the trail (user addendum)

Follow-up findings and bugs discovered mid-work are **normal work in the
normal form**: a new `finding.md` issue template (EARS ACs + an `Origin`
section naming the source report/finding and the item being worked), and the
`bug.md` template gains the same `Origin` section. Convention (documented,
claim-workflow posture, not gatable): when an origin issue exists, comment on
it referencing the new issue — the trail runs both ways. The inbox-triage doc
routes through the same door. The gate keeps enforcing what it can see
offline: a `follow-up` finding must carry *some* issue ref; the form of that
issue lives on GitHub and stays convention + template.

### 2. Publication tool — `publish_review.sh` (github-issues module, network, best-effort)

`bash scripts/process/publish_review.sh <report.md> [--campaign]` creates the
GitHub issue with the report as body (prompt, result, findings — full
visibility), prints the issue number to write into `issue:`. With a campaign:
creates (or reuses) the campaign parent issue and links the report issue to it
("Part of #N" reference; native sub-issue linking is a GitHub API nicety the
tool attempts via `gh`, falling back to the body reference — best-effort, same
posture as `new_issue.sh`/`gh_board.py`). The tool never edits the registry
and is never a gate.

### 3. Hermetic binding — gate extension in `check_issues.py` (github-issues module)

Offline, over the committed report files:

**Hard:**
- A malformed header (`review:`/`audit:` missing, unparseable `FINDING` line)
  — malformed structure is silent loss, exactly the telemetry/attestation rule.
- A report with neither `issue: <ref>` nor `publish-waived: <reason>` — in a
  GitHub-issues project, an unpublished review is invisible review; the waiver
  is the named, auditable escape (offline repos, private audits).
- A `FINDING … action=follow-up` with `issue=-` — a follow-up nobody tracks is
  a finding that will be forgotten; this is the parity gap→issue rule applied
  to findings.
- Reports sharing a `campaign:` slug that disagree on `campaign-issue:` — a
  split campaign is not bundled.
- A `campaign:` set on a published report with no `campaign-issue:` ref.

**Soft (note):**
- `sev=blocker` finding with `action=accept` — legal (judgment may accept even
  a blocker with cause) but worth a visible note.

**Silent:** no reports directory / no report files — binding is opt-in by
artifact existence (exactly like plans without a `tier:` line); a perpetual
"no audits yet" note would be noise, not information.

**Not checked (honest ceiling):** that the issue content matches the report,
that the prompt was truly the one used, that findings are complete — the gate
sees files, not history; truthfulness stays attested, as with `REVIEW` lines.

### Wiring (SP30 pattern, minimal)

- `verification-independence.md`: Tier 3 reviews and audit campaigns produce a
  report file; the `REVIEW` journal line stays the attestation SSOT, the
  report is the full record. Tier 2 reports encouraged, not demanded.
- `workflow.md` Review phase: one sentence — findings-producing reviews write
  the report and (github-issues) publish it.
- `github-issues` module doc: new section (format, grammar, tool, gate rules,
  campaign bundling).
- `journal-state-plans.md`: name the reviews/ neighbor beside plans/.

## Non-goals / alternatives considered

- **Auto-publishing from CI:** rejected — network write in the pipeline
  inverts the hermetic posture; publication stays a human/agent-invoked tool.
- **Making the report mandatory for every review:** rejected — a Tier 1 quick
  review would drown in ceremony; the duty scales (Tier 3 + campaigns) and the
  gate only binds reports that exist.
- **Native sub-issue API as a hard dependency:** rejected — `gh` sub-issue
  support varies; body-reference fallback keeps the tool best-effort.
- **Findings inside the github-master snapshot:** deferred — the snapshot
  mirrors issue state, not review content; coupling them would widen the
  master schema for one consumer.

## Anchor Delta

`check_issues.py` gains the report/FINDING lint (module-gated, github_issues);
new `publish_review.sh`; module doc section; three doc touches
(verification-independence, workflow Review, journal-state-plans). No core
gate change, no schema change to registry/snapshot, no rule change.

## Feature Registry Trace

Template self-change; template tests are acceptance. New tests: grammar
hard/soft branches (malformed FINDING, follow-up without issue, unpublished
without waiver, campaign disagreement, blocker-accepted note, fenced ignored,
no-reports-dir note, non-UTF-8), tool present/absent by module, neutrality,
docs wiring assertions.

tier: 2
decisions: read SP22 (sync/gate separation) and SP30 (prose duty vs gate) as
constraints; new decision recorded here — review/audit reports as committed
artifacts with gated issue-binding; no existing record superseded.
review-waived: template-repo slice; independent fresh-context review runs before push (same session pattern as SP28-SP31)
