# Refute — attack gate code before the first review round

Gate code decides what may reach the integration branch: `scripts/process/`,
`.githooks/`, the gate runner's configuration and the make targets a hook or
the merge train calls. A defect there does not break one feature, it lets
every later defect through — or blocks every later push.

Downstream, gate changes needed four and more review rounds, and nearly every
round found a case the author had not thought of: an amend next to the
reviewed commit, a merge train whose suite runs one make level deeper, a check
that said "OK" because a tool was missing. Tests written by the author test
the author's picture of reality. A fresh agent whose only job is to break the
change tests a different one — and costs minutes, not a review round.

## When

Before the first review round of every change that touches gate code. Again
after a fix round that changed gate code (the fix gets refuted, not the whole
branch). Not for plain documentation or product code.

## Who

A fresh agent — not the implementing session, no access to its context. It
reads the change and its tests, builds scratch repositories outside the
project, and never edits the project or pushes. Same model family is fine;
the stance (refute) is what counts.

## The brief

Copy, fill in the angle brackets, hand it over:

    You are an independent, adversarial reviewer. Work only in scratch
    directories outside the repository; do not modify it, do not push.
    When loading project modules directly, set sys.dont_write_bytecode first.

    Subject: <files / functions> — intended semantics: <two to five rules>.

    Try hard to find, with concrete reproductions:
    (a) BYPASSES — what should be refused but passes. Build the shapes real
        work produces: amend, rebase, reset + recommit, cherry-pick, a side
        branch merged in, merges with main (clean and with conflicts, resolved
        each way), the merge train's staging chain with several passengers,
        passengers without review, octopus and `-s ours` merges.
    (b) FALSE POSITIVES — what should pass but is refused: the normal daily
        flows above, the attestation commit, fast-forwards, main moving on.
    (c) FAIL-OPEN — errors, timeouts, missing tools that make it pass silently.
    (d) THE ENVIRONMENT MATRIX — run it the way production runs it: through
        the make target (MAKELEVEL 1), inside the pre-push hook, with and
        without `gh`, in a shallow clone, with only a local main, with a
        default branch not called main.

    Report per scenario PASS/FAIL against the intended semantics, the exact
    commands for every failure, a severity (BLOCKER/MAJOR/MINOR), and what you
    could not test.

## What happens with the findings

Every FAIL is fixed and becomes a regression test that fails against the
version before the fix — or it is accepted on purpose with a `DECISION` line
naming why. Then one line in the plan, so the reviewer sees what was attacked:

    REFUTE work=<id> round=<r>: <n> scenarios, <k> findings — <fixed / DECISION …>

Each plan records its own: the line names that plan's work (its file name,
with or without the date, or its issue), a round and what was found. A line
of one stacked plan does not cover another, and a bare `REFUTE work=<id>`
is a mention, not a record. After a fix round, the delta re-review
(`--since`) wants a new line: the fix gets refuted, not the first line reused.

The review bundle warns when a diff touches gate code and a plan carries no
such line (a warning, not a block: the rule is observed before it gates).
It approximates gate code by path — `scripts/process/`, `.githooks/`,
`.github/workflows/`, `Makefile`, `.pre-commit-config.yaml` — so a Makefile
change to a product target warns too; say so in the plan (the warning stays,
the reviewer weighs it) instead of refuting
it. A line quoted as an example (in a code block, a comment, or with the
brief's `<id>` placeholder, or wrapped in backticks) does not count.
