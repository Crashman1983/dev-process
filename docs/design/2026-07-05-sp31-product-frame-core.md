# SP31 — Product frame as a core artifact (PRODUCT.md)

## Problem

An adopter repo gets no product frame from the template. The rendered anchor
carries process kernel only; the onboarding dialogue collects "product goal,
users, first slice" into `.process-work/` notes that **nothing ever reads
again** — no phase, no command, no gate, not `/prime` (verified in the
2026-07-05 audit). The direction Kenni's PRD gave the LLM during development
(anchor triple CLAUDE.md + PRD + ARCHITECTURE.md, reloaded at execute/review,
read by prime) has no counterpart in the framework. Consequences:

- The LLM develops without knowing what the product is for, for whom, and what
  is deliberately out of scope — non-goals are the cheapest guardrail there is,
  and the framework cannot express them.
- Product decisions made in discussion (outside the change flow) have no
  trigger (SP30 hooks fire on the dev cycle only) and no home besides a
  retroactive ADR nobody is prompted to write.

## Decision

`PRODUCT.md` becomes a **core artifact** (user decision: core, not module —
a project that adopts the process has a product frame to maintain, per
definition), with an always-on core gate, wired into the flow by the SP30
pattern. The **initial creation happens in the init/brainstorming dialogue**
(user requirement): the start-here onboarding already asks exactly the frame
questions — its output artifact is now `PRODUCT.md`, not loose notes.

### The artifact

`PRODUCT.md` at the adopter repo root (beside `ARCHITECTURE.md`): Purpose,
Users, Goals, **Non-goals**, Constraints, Scope now. A living state document —
scope shifts are edits to it, which routes product decisions through the
normal cycle (tier routing, review, decisions check) and closes the
outside-the-cycle trigger gap. It carries one machine-readable state line:
`status: not-onboarded` (as shipped) or `status: onboarded` (flipped by the
onboarding dialogue when the sections hold real facts).

### The gate — `check_product_frame.py` (core, always on)

Mechanical honesty only, prose quality stays with the review:

- **Hard:** `PRODUCT.md` missing (it is core and ships with the template —
  deleting it breaks the frame; unlike the *optional* arch-docs overview,
  absence is a violation, not pre-adoption).
- **Hard:** no recognizable `status:` line, or a value outside
  `not-onboarded|onboarded` (unreadable state axis, mirrors the decisions
  gate's enum posture).
- **Soft (note):** `status: not-onboarded` — expected pre-init; the note names
  the onboarding dialogue as the fill path. Placeholders are allowed here.
- **Hard once `status: onboarded`:** leftover placeholder lines — an onboarded
  frame still holding placeholders is a false claim (arch-docs can only be
  soft here because it has no onboarded marker; the marker is what buys the
  harder check honestly).
- **Hard:** an `ADR-NNNN` reference that does not resolve (adr/ is core).
- **Hard when the registry exists:** a `STORY-NNNN` reference that does not
  resolve; **soft note** when the feature-registry module is off (not
  checkable — honest degradation).
- Fenced code blocks are ignored for refs and placeholders; non-UTF-8 hard.

### The wiring (SP30 pattern)

- **start-here.md:** the onboarding dialogue's output is `PRODUCT.md`
  (greenfield: fill from the dialogue answers and flip the status; brownfield:
  inventory the real product into it); First-run checklist and Definition of
  ready name it.
- **workflow.md:** Brainstorm reads `PRODUCT.md` as a constraint — a design
  that serves no stated goal or violates a non-goal must say so; a scope shift
  updates `PRODUCT.md` in the same change. Plan names the product goal the
  change serves, or that it is product-neutral. Review's category list gains
  the product frame.
- **review-checklist.md:** new "Product frame" section — serves a stated goal
  (or product-neutral)? violates a non-goal (then the frame changes
  deliberately in the same change, or the change does not merge)? shifts scope
  while `PRODUCT.md` stays untouched (silent drift)?
- **journal-state-plans.md:** Tier 2+ plan names the goal served or declares
  product-neutrality — same prose-duty posture as the SP30 decision context,
  same honesty note (judged at review, deliberately not a gated field).
- **Anchors (all three) + `/prime`:** `PRODUCT.md` joins the "for normal work
  also read" pointers and the prime rehydration set.

## Non-goals / alternatives considered

- **Opt-in module** (arch-onboarding pattern): rejected by user decision —
  core; the "when the process is not worth it" honesty already lives at
  install level (minimal profile skips the *process*, not its frame).
- **Goal-IDs + story→goal mapping gate:** deferred — would need a schema and
  invites ritual mapping; the checklist question covers the substance. Can
  land later if practice shows silent drift survives review.
- **PRD long-form document** (Kenni-style multi-section spec): deliberately
  not — the frame is a compass, not a spec; features live in the registry,
  decisions in the records. Keeping it one page is what keeps it read.

## Anchor Delta

New root artifact `PRODUCT.md.jinja`; new core gate script
`check_product_frame.py` + `gate_runner` core entry (`product-frame`, key
`None`); `start-here.md` (onboarding output, first-run, definition of ready),
`workflow.md.jinja` (Brainstorm/Plan/Review), `review-checklist.md` (new
section), `journal-state-plans.md` (plan duty), three anchor templates, both
prime commands (`.claude/commands/prime.md`, `.github/prompts/prime.prompt.md`)
and the `.claude/commands/review.md` category enumeration (gains
`product frame`); doc-drift `SCAN_FILES` gains `PRODUCT.md` (post-review fix).
README (Eckpunkte + status), CAPABILITIES.md (one clause). No rule change —
rule 2/4 already carry plan- and decision-duties; the frame is an artifact
those duties now see.

## Feature Registry Trace

Template self-change; template tests are acceptance. New
`tests/test_product_frame.py`: rendered presence + neutrality; core gate listed
with all modules off; seed green with not-onboarded note; missing file hard;
onboarded+placeholder hard vs not-onboarded+placeholder green; bad/missing
status hard; dead ADR ref hard, fenced ignored; STORY ref hard with registry /
soft note without; non-UTF-8 hard. `test_core_docs.py`: workflow phases and
checklist section and plan duty and anchor/prime pointers assert the wiring.
`test_manifest_ci.py`: core-gate test extends to `product-frame`.

tier: 2
decisions: read ADR-0001 (record decisions, seed) and the SP30 design (prose
duty over gate) as constraints; new decision recorded here — product frame as
core artifact with onboarded-marker gate; no existing record superseded.
review-waived: template-repo slice; independent fresh-context review runs before push (same session pattern as SP28-SP30)
