# Refute — attack a change before its first review round

A refute is a fresh agent whose only job is to break the change. Tests
written by the author test the author's picture of reality; the refuter tests
a different one — and costs minutes, not a review round. Downstream it found
more than the review rounds before it, again and again: half of what one
run found had been introduced by the previous fix round, and the most
expensive blockers came from a second owner of a rule the change did not
know about.

Gate code needs it most. It decides what may reach the integration branch —
`scripts/process/`, `.githooks/`, the gate runner's configuration and the
make targets a hook or the merge train calls — so a defect there does not
break one feature, it lets every later defect through, or blocks every later
push.

## When

Scaled to the tier (`risk-tiers.md`):

| Tier | Refute |
|---|---|
| 0 | none |
| 1 | optional — worth one run when the change parses input or runs concurrently (persistence, paths and subprocesses already lift a change to Tier 2); record the line in the journal, there is no plan or bundle |
| 2 | no separate run: the review itself works through the brief below — owner and second reader, fail-open, the catalog's edge cases, evidence — and answers it in its report. A separate run before the first review round only where the plan's threat and failure question names data loss or concurrency (gate code: next row); a fix round gets regression tests, not a new run |
| 3, and gate code at any tier | before the first review round, and again after every fix round that changed code (the fix gets refuted, not the whole branch) |

Plain documentation needs none.

## Who

A fresh agent — not the implementing session, no access to its context. It
reads the change, its plan and tests, builds scratch repositories outside
the project, and never edits the project or pushes. Same model family is
fine; the stance (refute) is what counts. It gets the diff, the plan with
its acceptance criteria and this document — not the previous round's
report, so it does not search where the last one did.

## What the refuter checks, in this order

One run is about fifteen scenarios; spend them in this order, and skip what
the change does not touch.

1. **Is there already an owner?** Does the diff introduce a rule, a path
   list, a pattern, a parser or a lookup that existing code already owns
   (mandatory rule 4)? Search the repository for it. A finding is a
   **differential test**: an input on which the new code and the existing
   owner judge differently. "Looks similar" is a note, not a finding. Only
   what the diff introduces is checked; a duplicate merely noticed on the
   way becomes an issue.
2. **Is a failure read as success?** Make the things the change relies on
   fail — a command exits non-zero, a tool is missing, a reference does not
   exist, a call times out — and check that the result fails closed, never
   "nothing found" and green.
3. **Edge cases**, from the failure catalog
   (`docs/process/failure-catalog.md`): only the classes the change touches.
4. **Does the evidence hold?** Remove one branch of the new code: does a
   test go red? Are the plan's red/green claims true?
5. **Is there a pattern?** After the findings, one line: do they share a
   cause — the same kind of input read the same wrong way — that one owner
   would close? Name that owner, or write "no common cause". Findings that
   share a cause, fixed one by one, come back in the next round in another
   form (downstream: four review rounds on one guard, one cause, and the
   rewrite came only in the fourth).

Gate code adds, within the same run:

- **Bypasses** — what should be refused but passes. Build the shapes real
  work produces: amend, rebase, reset + recommit, cherry-pick, a side branch
  merged in, merges with main (clean and with conflicts, resolved each way),
  the merge train's staging chain with several passengers, passengers
  without review, octopus and `-s ours` merges.
- **False refusals** — what should pass but is refused: the normal daily
  flows above, the attestation commit, fast-forwards, main moving on.
- **The environment matrix** — run it the way production runs it: through
  the make target (MAKELEVEL 1), inside the pre-push hook, with and without
  `gh`, in a shallow clone, with only a local main, with a default branch
  not called main.

The refuter writes no fixes, no style remarks and no design opinions — that
is the review's and the implementing session's work.

## Edge cases

The classes come from `docs/process/failure-catalog.md` — the one list; a
confirmed finding of a class not listed there adds the class in the fix.

## The brief

Copy, fill in the angle brackets, hand it over:

    You are an independent, adversarial reviewer. Work only in scratch
    directories outside the repository; do not modify it, do not push.
    When loading project modules directly, set sys.dont_write_bytecode first.

    Subject: <files / functions> — intended semantics: <two to five rules,
    or the plan's acceptance criteria>.

    In this order, about fifteen scenarios in all:
    1. OWNER — does the diff re-implement a rule existing code already owns?
       Prove it with an input on which both judge differently.
    2. FAIL-OPEN — make what it relies on fail (non-zero exit, missing tool,
       missing reference, timeout); it must fail closed.
    3. EDGE CASES — the classes of docs/process/failure-catalog.md that
       the change touches.
    4. EVIDENCE — remove one branch: does a test go red? Are the plan's
       red/green claims true?
    <gate code only: 5. BYPASSES, FALSE REFUSALS and the ENVIRONMENT MATRIX
    as docs/process/refute.md lists them.>
    Then PATTERN — one line: the cause the confirmed findings share and the
    one owner that would close them all, or "no common cause".

    Run every scenario against the change AND against the integration
    branch. Report each as CONFIRMED (with the failing test, its output, and
    NEW — passes on the integration branch — or PRE-EXISTING) or HELD, with a
    severity (BLOCKER/MAJOR/MINOR) and what you could not test. No fixes.

## What happens with the findings

Every NEW finding is fixed and becomes a regression test that fails against
the version before the fix — or it is accepted on purpose with a `DECISION`
line naming why. A PRE-EXISTING finding becomes an issue; it is not this
work's fix round.

A second owner proven by a differential test blocks at every tier, unless the
plan carries a `DECISION` naming why the rule has two owners — a deliberate
copy across a boundary whose divergences are named and tested, a technical
boundary (a stdlib-only script, a hook without the project's environment),
or a double check that takes its rule from one source. Otherwise the fix
reuses the owner; that is usually less code than the copy.

Then one line in the plan, so the reviewer sees what was attacked:

    REFUTE work=<id> round=<r>: <n> scenarios, <k> findings — <fixed / DECISION …>

Each plan records its own — an active plan under `.process-work/plans/` or a
Spec Kit plan `specs/<dir>/plan.md`: the line names that plan's work (its file
name, with or without the date, the spec directory's name, or its issue), a
round and what was found. A line of one stacked plan does not cover another,
and a bare `REFUTE work=<id>` is a mention, not a record. After a fix round,
the delta re-review (`--since`) wants a new line: the fix gets refuted, not
the first line reused. A line is old when the plan's own path at the delta's
start already had that round, or when a plan at the start (archived ones
included) carried the same line — same round, same text after the colon —
for this plan's work, or in a plan that has left its path since (moved,
archived or merged; its id may have changed along). So a reformatted, moved,
archived-and-copied or merged old line is no new round, another work's
identical line in a plan still in place does not make this plan's new line old, and a second plan of the same issue neither lends nor takes one:
its own new line says what it found. An old line whose text is edited and
that moves to another path reads as new — edit a record, and it is yours.

Which plans are checked: every active plan in `.process-work/plans/`, and a
Spec Kit plan `specs/<dir>/plan.md` only while it is under work — the branch
changes `specs/<dir>/`, or its `tasks.md` has an unticked task. Spec Kit plans
never archive; a finished one (or a product document at `specs/<x>/plan.md`)
is not asked for a new round in every later delta. `--plan <name>` bundles
what it names either way (a Spec Kit plan by its directory or its label).

The review bundle warns when a bundled plan declares Tier 3, or a diff
touches gate code at any tier, and a plan carries no such line (a warning,
not a block: the rule is observed before it gates). A Tier 2 plan that names
data loss or concurrency is not detected — the reviewer checks its line. A
Tier 2 bundle carries the brief's questions for the reviewer to answer. A
delta re-review asks for a new line at Tier 3, and below it when the delta
touches gate code — the table's fix-round run.
It approximates gate code by path — `scripts/process/`, `.githooks/`,
`.github/workflows/`, `Makefile`, `.pre-commit-config.yaml` — so a Makefile
change to a product target warns too; say so in the plan (the warning stays,
the reviewer weighs it) instead of refuting
it. A line quoted as an example (in a code block, a comment, or with the
brief's `<id>` placeholder, or wrapped in backticks) does not count. Comments
are read as Markdown renders them: `<!--` at the start of a line hides
everything up to `-->` (the rest of the file when it never closes); inside
running text only a comment closed in the same paragraph hides anything, and
a `<!--` inside backticks is code. Known limits (`check_review.readable`):
the `<!-->` form, comments inside block quotes or deep list items, other HTML
block kinds and entity-escaped markers are not modelled. `attest.py` reads
`ROOT-CAUSE` lines the same way: a fenced, commented or placeholder
(`<cause>`) line is no cause.
