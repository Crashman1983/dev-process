# /finish

Close a feature branch cleanly — the merge tail as one verdict instead of a
ritual scattered over four docs. Run:

    uv run scripts/process/finish.py

The checker is read-only: it verifies the branch is actually done (clean
worktree, clearing REVIEW pass for every active tier-2+ plan, gate suite
green) and then prints the exact remaining steps in order — archive the
plan(s) on the branch, merge, delete the branch, remove the worktree,
publish/prune. Execute the printed steps; do not improvise the order
(`docs/process/commits.md`, Merging — the plan archives BEFORE the merge,
and merge leaves no residue).

A push whose hook may run tests for minutes is never waited out inside a
tool call: produce the evidence in the background first (the project's
certify step, where one exists), then push; on a busy-lane abort do other
work and push again later — never a retry loop (the `git-hooks` module doc).

Then let the checker execute the deterministic part instead of retyping
it:

    uv run scripts/process/finish.py --apply            # archive commit + rebase, stops before the merge
    uv run scripts/process/finish.py --apply --tests "<full suite command>"   # … then merge, push, delete branch
    uv run scripts/process/finish.py --apply --tests-passed                  # same, asserting the suite already ran

Every step prints its command; the first failure stops the run in a state
git explains. The merge only happens behind the batch's FULL suite (test
economy, `docs/process/testing.md`).

BLOCKED means exactly one thing: the tail is not reachable yet — most often
a missing clearing pass (run `/review`) or red gates. Do not merge around a
BLOCKED verdict; the production failures this command exists for were all
merges past an unfinished tail.
